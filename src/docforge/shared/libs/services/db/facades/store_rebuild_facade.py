# ====== Code Summary ======
# StoreRebuildFacade — the Qdrant phase of rebuild_index (no content re-embed). It creates a fresh
# physical ``col_<hex>_r<ts>`` from the CURRENT schema (so newly semantic/lexical fields get their named
# vectors, and meta BM25 vectors get the IDF modifier), copies every point batch by batch keeping only
# declared vectors and DROPPING every ``meta_*_bm25`` vector (mixed encoders otherwise) — and, when the
# old content sparse vector came from another sparse provider (IDF modifier mismatch, or a baseline
# whose sparse half differs from the config) or is absent while the config has a sparse slot,
# re-encoding it from the Postgres chunk text in the same upsert — re-checking its
# own job row between batches (a cancel or a reap aborts BEFORE the swap), stamps the copy COMPLETE,
# then swaps it under the stable name through ``StoreSwapper``:
#   - first rebuild (the stable name is a physical collection): delete it, then create the alias. A
#     crash between the two leaves the stamped generation un-aliased; every store-addressing path
#     (``QdrantAliasApi.resolve_or_adopt``) re-adopts it, so no ingest recreates an empty store over it;
#   - later rebuilds: ONE atomic ``update_collection_aliases`` (delete + create), then drop the old.
# Any failure BEFORE the swap drops the temporary collection; the old store stays live and untouched.

# ====== Standard Library Imports ======
import time
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.embed.blob import EmbedBlobResolver
from shared_libs.public_models import VectorLayout
from shared_libs.services.db.index_embed_baseline import EmbedBaseline
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import CollectionApi
from shared_libs.services.db.qdrant import (
    DOCUMENT_ID_KEY,
    REBUILD_SUFFIX,
    DeclaredVectors,
    QdrantAliasApi,
    QdrantClient,
    QdrantCollectionApi,
    QdrantStoreCopyApi,
    VectorNames,
)

# ====== Local Project Imports ======
from .content_sparse_reencoder import ContentSparseReencoder
from .helpers import DatabaseHelpers
from .index_rebuild_payloads import AbortProbe, RebuildCancelledError, StoreCopyResult
from .meta_vector_sync_helpers import MetaVectorSyncHelpers
from .store_swapper import StoreSwapper


class StoreRebuildFacade(LoggerClass):
    """Recreate a collection's Qdrant store from its current schema and swap it in."""

    def __init__(
        self, postgres: PostgresClient, qdrant: QdrantClient, swapper: StoreSwapper | None = None
    ) -> None:
        """
        Args:
            postgres (PostgresClient): The schema truth the new store is derived from.
            qdrant (QdrantClient): The vector store being rebuilt.
            swapper (StoreSwapper | None): Generation settle/swap (default: one over ``qdrant``).
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant
        self._swapper = swapper or StoreSwapper(qdrant)

    async def rebuild(
        self, collection_id: uuid.UUID, batch_size: int, should_abort: AbortProbe | None = None
    ) -> StoreCopyResult:
        """
        Copy the store into a fresh schema-derived collection and swap it under the stable name.

        Args:
            collection_id (uuid.UUID): The collection to rebuild.
            batch_size (int): Points per scroll/upsert batch.
            should_abort (AbortProbe | None): The job-row probe, checked between batches and right
                before the swap.

        Raises:
            RebuildCancelledError: The probe fired — the temp was dropped, the old store is untouched.

        Returns:
            StoreCopyResult: The new physical name, copied points and documents, swap mode.
        """
        client = self._qdrant.raw
        stable = DatabaseHelpers.qdrant_collection_name(collection_id)
        # 1. Resolve the live store (re-adopting a stranded complete generation); no space at all →
        #    nothing to rebuild (the first ingest declares every vector).
        if not await QdrantAliasApi.resolve_or_adopt(client, stable):
            return StoreCopyResult(physical=None)
        old = await self._swapper.settle(
            stable, await QdrantAliasApi.resolve_physical(client, stable)
        )
        temp = f"{stable}{REBUILD_SUFFIX}{time.time_ns()}"
        try:
            # 2. Create the new store from the CURRENT schema, copy every point, then stamp it
            #    complete — only after a last own-row check (a cancel must never reach the swap).
            result = await self._create_and_copy(collection_id, old, temp, batch_size, should_abort)
            await self._raise_if_aborted(should_abort)
            await QdrantAliasApi.mark_complete(client, temp)
        except BaseException:
            # 3. Pre-swap failure (or cancel): drop the temp, leave the old store live.
            await self._swapper.drop_quietly(temp)
            raise
        # 4. Swap the stable name onto the new store, then drop the old physical collection.
        result.first_rebuild = old == stable
        await self._swapper.swap(stable, old, temp, first=result.first_rebuild)
        return result

    @staticmethod
    async def _raise_if_aborted(should_abort: AbortProbe | None) -> None:
        """Raise ``RebuildCancelledError`` when the job row says stop."""
        if should_abort is not None and await should_abort():
            raise RebuildCancelledError("rebuild cancelled before the swap")

    def __reencoder(
        self, collection: object, old_declared: DeclaredVectors, layout: VectorLayout
    ) -> ContentSparseReencoder | None:
        """The content sparse re-encoder when the old store's content sparse cannot be copied.

        Besides an absent or modifier-mismatched vector, a known baseline whose SPARSE half differs
        from the config (another sparse provider/endpoint/model, same modifier) forces it too. An
        unknown baseline (never stamped) keeps the store-only check.
        """
        pipeline = getattr(collection, "pipeline", None)
        stored = getattr(collection, "indexed_embed_signature", None)
        sparse_changed = bool(stored) and not EmbedBaseline.sparse_matches(stored, pipeline or {})
        if not ContentSparseReencoder.needed(old_declared, layout, sparse_changed):
            return None
        embed_node = MetaVectorSyncHelpers.find_embed_node(pipeline or {})
        if embed_node is None:
            return None
        embedder, _config = MetaVectorSyncHelpers.rebuild_embedder(embed_node)
        return ContentSparseReencoder(self._postgres, embedder)

    async def __dense_dim(self, old: str, dense_on: bool) -> int:
        """The OLD store's content_dense size, or 0 when the config has no dense provider.

        Raises:
            ValueError: The config has a dense provider but the old store holds no dense vector
                (e.g. a sparse-only collection switched to dense) — a copy cannot invent vectors;
                re-ingest the documents instead.
        """
        if not dense_on:
            return 0
        try:
            return await QdrantStoreCopyApi.content_dense_dim(self._qdrant.raw, old)
        except ValueError as exc:
            raise ValueError(
                f"{exc} — the embed config now has a dense provider the stored vectors never used; "
                "an index rebuild copies vectors and cannot create them: re-ingest the documents"
            ) from exc

    async def _create_and_copy(
        self,
        collection_id: uuid.UUID,
        old: str,
        temp: str,
        batch_size: int,
        should_abort: AbortProbe | None,
    ) -> StoreCopyResult:
        """Create ``temp`` from the schema (+ the old store's extra indexes) and copy ``old`` into it."""
        client = self._qdrant.raw
        async with self._postgres.session() as session:
            schema = await CollectionApi.get_schema(session, collection_id)
            collection = await CollectionApi.get(session, collection_id)
        DatabaseHelpers.validate_vector_slugs(schema)
        # 1. The layout follows the embed CONFIG (strict: a broken embed blob fails the rebuild, never
        #    creates a guessed schema); the dense size is the OLD content vector's (content is copied,
        #    not re-embedded) — none without a dense provider.
        layout = EmbedBlobResolver.layout_or_raise(getattr(collection, "pipeline", None))
        await QdrantCollectionApi.ensure(
            client,
            temp,
            dense_dim=await self.__dense_dim(old, layout.dense),
            semantic_fields=[f.field_name for f in schema if f.semantic],
            lexical_fields=[f.field_name for f in schema if f.lexical],
            filterable_fields={
                f.field_name: DatabaseHelpers.payload_type_for(f.field_type)
                for f in schema
                if f.filterable
            },
            layout=layout,
        )
        await QdrantStoreCopyApi.copy_missing_indexes(client, old, temp)
        # 2. Copy batch by batch, keeping only declared non-meta-BM25 vectors; a content sparse
        #    vector from another encoder (or absent) is re-encoded from the chunk text instead.
        dense, sparse = await QdrantCollectionApi.declared_vectors(client, temp)
        reencoder = self.__reencoder(
            collection,
            DeclaredVectors.from_params((await client.get_collection(old)).config.params),
            layout,
        )
        dropped = {VectorNames.CONTENT_SPARSE} if reencoder is not None else set()
        result = StoreCopyResult(physical=temp, sparse_reencoded=reencoder is not None)
        documents: set[str] = set()
        async for records in QdrantStoreCopyApi.scroll(client, old, batch_size):
            await self._raise_if_aborted(should_abort)
            result.carried_vectors.update(QdrantStoreCopyApi.vector_names(records))
            extra = (
                await reencoder.encode([str(record.id) for record in records])
                if reencoder is not None
                else None
            )
            result.reencoded_sparse_points += len(extra or {})
            result.copied_points += await QdrantStoreCopyApi.upsert_batch(
                client, temp, records, dense | sparse, dropped, extra
            )
            documents.update(
                str(record.payload[DOCUMENT_ID_KEY])
                for record in records
                if record.payload and record.payload.get(DOCUMENT_ID_KEY)
            )
        result.document_ids = documents
        self.logger.info(
            f"Copied {result.copied_points} point(s) from '{old}' into '{temp}' "
            f"({result.reencoded_sparse_points} content sparse vector(s) re-encoded)"
        )
        return result


__all__ = ["StoreRebuildFacade"]

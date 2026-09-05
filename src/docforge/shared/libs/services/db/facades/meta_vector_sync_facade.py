# ====== Code Summary ======
# MetaVectorSyncFacade — populates a document's DOCUMENT-SCOPE metadata NAMED VECTORS (semantic dense
# + lexical sparse) on every one of its chunk Qdrant points, so a metadata-only search resolves to a
# vector that actually holds data. The value lives once per document in Postgres; a document-scope
# value is uniform, so the SAME meta vector rides on all the document's chunk points. Mirrors
# FilterSyncFacade but writes VECTORS (update_vectors) instead of payload scalars: it rebuilds the
# collection's OWN embedder from its ingestion blob and embeds only the short metadata VALUES — never
# the content. The values are embedded in ONE batched pass per axis (dense / sparse) and written in a
# SINGLE batched update_vectors call, so the sync is a bounded handful of round-trips regardless of
# field or chunk count. Idempotent, non-destructive (content vectors untouched), a clean no-op when
# the document has no indexed chunk or no semantic/lexical value. The write-side hook and the
# collection-wide backfill both go through the SAME per-document sync; the backfill pages through the
# collection's documents so a large collection never loads whole into memory.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.embed.base import BaseEmbedderNode
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import ChunkApi, CollectionApi, DocumentApi
from shared_libs.services.db.qdrant import (
    QdrantClient,
    QdrantCollectionApi,
    QdrantIndexApi,
    QdrantPoint,
    SparseVec,
)

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers
from .meta_vector_sync_helpers import MetaVectorSyncHelpers


class MetaVectorSyncFacade(LoggerClass):
    """Populate document-scope metadata named vectors (dense/sparse) onto every chunk's point."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth (metadata values + embedder blob + flags).
            qdrant (QdrantClient): The vector store whose named meta vectors are populated.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant

    # A large collection's backfill pages through its documents rather than loading every row at
    # once: each page is processed then dropped, bounding memory to one page regardless of size.
    __BACKFILL_PAGE_SIZE = 500

    async def __build_meta_vectors(
        self,
        embedder: BaseEmbedderNode,
        rows: list[tuple[str, Any, bool, bool]],
        declared_dense: set[str],
        declared_sparse: set[str],
    ) -> tuple[dict[str, list[float]], dict[str, SparseVec]]:
        """Embed the document's metadata values into their named vectors — ONE batched pass per axis.

        A document carries only a handful of short metadata values, so both axes are embedded in a
        single batched call each rather than one forward pass per field — the vectors are identical
        whichever route a provider uses, so per-axis batching is a strict win over a per-field
        combined route (N field round-trips collapse to at most two).
        """
        # 1. Plan (pure) which declared named vector each value feeds — dense and/or sparse buckets.
        dense_fields, sparse_fields = MetaVectorSyncHelpers.plan_meta_axes(
            rows, declared_dense, declared_sparse
        )
        # 2. One batched forward pass per axis, mapped back to its named vectors.
        dense = await self.__embed_dense_axis(embedder, dense_fields)
        sparse = await self.__embed_sparse_axis(embedder, sparse_fields)
        return dense, sparse

    async def __embed_dense_axis(
        self, embedder: BaseEmbedderNode, fields: list[tuple[str, str]]
    ) -> dict[str, list[float]]:
        """Embed every semantic value into its dense meta vector in ONE batched forward pass."""
        if not fields:
            return {}
        names = [name for name, _ in fields]
        vectors = await embedder._embed_dense([text for _, text in fields])
        return dict(zip(names, vectors, strict=True))

    async def __embed_sparse_axis(
        self, embedder: BaseEmbedderNode, fields: list[tuple[str, str]]
    ) -> dict[str, SparseVec]:
        """Embed every lexical value into its sparse meta vector in ONE batched pass.

        A dense-only embedder has no sparse axis and returns None for the whole batch; the lexical
        vectors are then skipped loudly rather than failing this best-effort repair hook.
        """
        if not fields:
            return {}
        names = [name for name, _ in fields]
        vectors = await embedder._embed_sparse([text for _, text in fields])
        if not vectors:
            self.logger.warning(
                f"Embedder has no sparse axis — {len(fields)} lexical meta vector(s) skipped"
            )
            return {}
        return {
            name: SparseVec(indices=vector.indices, values=vector.values)
            for name, vector in zip(names, vectors, strict=True)
        }

    async def sync_document_meta_vectors(self, document_id: uuid.UUID) -> int:
        """
        Populate a document's semantic/lexical document-scope metadata vectors on all its points.

        The values are read once from Postgres, embedded with the collection's OWN embedder, and
        written (a partial named-vector update) onto every indexed chunk point — a document-scope
        value is uniform, so the same meta vector rides every chunk. Never re-embeds content;
        re-running yields the same vectors (idempotent). Skips cleanly when the document has no
        indexed chunk or no semantic/lexical value.

        Args:
            document_id (uuid.UUID): The document to synchronise.

        Returns:
            int: The number of chunk points patched (0 when there is nothing to embed or to carry).
        """
        # 1. Read the document, its collection (embedder blob), its searchable values + point ids.
        async with self._postgres.session() as session:
            document = await DocumentApi.get(session, document_id)
            if document is None:
                return 0
            collection = await CollectionApi.get(session, document.collection_id)
            if collection is None:
                return 0
            rows = await DocumentApi.get_searchable_metadata(session, document_id)
            chunk_ids = await ChunkApi.get_indexed_ids_for_document(session, document_id)

        # 2. No value to embed, or no point to carry it → clean no-op.
        if not rows or not chunk_ids:
            return 0

        # 3. Rebuild the embedder from the collection's ingestion blob (drifted blob fails loudly).
        embed_node = MetaVectorSyncHelpers.find_embed_node(collection.pipeline)
        if embed_node is None:
            self.logger.warning(
                f"Collection {document.collection_id} has no embed node — meta vectors skipped"
            )
            return 0
        embedder, _config = MetaVectorSyncHelpers.rebuild_embedder(embed_node)

        # 4. Embed each value into its DECLARED named meta vector (guarded against undeclared names).
        name = DatabaseHelpers.qdrant_collection_name(document.collection_id)
        declared_dense, declared_sparse = await QdrantCollectionApi.declared_vectors(
            self._qdrant.raw, name
        )
        dense, sparse = await self.__build_meta_vectors(
            embedder, rows, declared_dense, declared_sparse
        )
        if not dense and not sparse:
            return 0

        # 5. The SAME meta vectors on every chunk point (partial update — content vectors untouched).
        points = [
            QdrantPoint(point_id=str(chunk_id), payload={}, dense=dict(dense), sparse=dict(sparse))
            for chunk_id in chunk_ids
        ]
        await QdrantIndexApi.update_vectors(self._qdrant.raw, name, points)
        self.logger.info(
            f"Synced {len(dense)} dense + {len(sparse)} sparse meta vector(s) onto "
            f"{len(chunk_ids)} point(s) for document {document_id}"
        )
        return len(chunk_ids)

    async def backfill_collection_meta_vectors(self, collection_id: uuid.UUID) -> tuple[int, int]:
        """
        Run the per-document meta-vector sync across every document of a collection (one-off backfill).

        The maintenance path for data ingested before the meta vectors were populated: no content
        re-embed, only the short metadata values embedded and written per document. Idempotent.

        SCOPE: backfills DOCUMENT-scope semantic/lexical fields only. Chunk-scope semantic values are
        embedded per chunk at INGEST (their named vector is declared at collection creation), so they
        need no backfill. A chunk-scope field toggled semantic AFTER first ingest needs a named vector
        Qdrant cannot add to a live collection — the collections reconcile flags that as reindex-
        required, so the honest fix is a reingest, never a silent post-hoc vector add.

        Args:
            collection_id (uuid.UUID): The collection whose documents are backfilled.

        Returns:
            tuple[int, int]: (documents that received meta vectors, total points patched).
        """
        # 1. Page through the collection's documents so a huge collection never loads whole into
        #    memory: each page is fetched, processed, then dropped. The per-document sync is
        #    idempotent, so a document that shifts pages under a concurrent insert is at worst
        #    re-synced (same vectors), never corrupted.
        documents_synced = 0
        points_patched = 0
        offset = 0
        while True:
            async with self._postgres.session() as session:
                page = await DocumentApi.list_for_collection(
                    session, collection_id, limit=self.__BACKFILL_PAGE_SIZE, offset=offset
                )
            # 2. Accumulate what was actually patched (documents with values AND indexed chunks).
            for document in page:
                patched = await self.sync_document_meta_vectors(document.id)
                if patched:
                    documents_synced += 1
                    points_patched += patched
            # 3. A short page is the last one — stop before an empty round-trip.
            if len(page) < self.__BACKFILL_PAGE_SIZE:
                break
            offset += self.__BACKFILL_PAGE_SIZE

        self.logger.info(
            f"Backfilled meta vectors on collection {collection_id}: "
            f"{documents_synced} document(s), {points_patched} point(s)"
        )
        return documents_synced, points_patched


__all__ = ["MetaVectorSyncFacade"]

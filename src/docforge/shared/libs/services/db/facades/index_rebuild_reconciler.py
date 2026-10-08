# ====== Code Summary ======
# IndexRebuildReconciler — the post-swap RECONCILIATION of a rebuild_index job: re-apply chunk enabled
# overrides, purge points of documents deleted during the copy, then derive needs_reindex honestly — a
# chunk-scope semantic vector no point carries keeps it raised: only a reingest can fill it — as does a
# changed DENSE embed space; a changed sparse space the copy re-encoded clears it.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.embed.blob import EmbedBlobResolver
from shared_libs.public_models import FieldScope
from shared_libs.services.db.index_embed_baseline import EmbedBaseline
from shared_libs.services.db.index_signature import CollectionIndexSignature
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import CollectionApi, RebuildJobApi
from shared_libs.services.db.qdrant import ENABLED_KEY, QdrantClient, QdrantIndexApi, VectorNames

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers
from .index_rebuild_payloads import RebuildReconcileResult, StoreCopyResult
from .index_state_facade import IndexStateFacade


class IndexRebuildReconciler(LoggerClass):
    """Post-swap convergence of a rebuilt store with Postgres + the honest ``needs_reindex`` flag."""

    def __init__(
        self, postgres: PostgresClient, qdrant: QdrantClient, index_state: IndexStateFacade
    ) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth (overrides, documents, baseline).
            qdrant (QdrantClient): The vector store (override + orphan reconciliation writes).
            index_state (IndexStateFacade): The declared-vs-needed view (post-swap re-check).
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant
        self._index_state = index_state

    async def _unfilled_chunk_fields(
        self, collection_id: uuid.UUID, copy: StoreCopyResult
    ) -> list[str]:
        """Chunk-scope semantic fields whose vector no copied point carries — only a reingest fills them.

        A rebuild copies content vectors as they are and the meta-vector backfill is document-scope,
        so a chunk-scope vector the old store never carried stays empty. Conservative: a field no
        chunk has a value for also lands here (a reingest is then a harmless no-op that clears it).
        """
        if not copy.copied_points:
            return []
        async with self._postgres.session() as session:
            schema = await CollectionApi.get_schema(session, collection_id)
        return sorted(
            f.field_name
            for f in schema
            if f.scope == FieldScope.CHUNK
            and f.semantic
            and VectorNames.field_dense(f.field_name) not in copy.carried_vectors
        )

    async def _apply_overrides(self, collection_id: uuid.UUID, name: str) -> int:
        """Re-apply every chunk's ``enabled_override`` onto the store's ``enabled`` payload."""
        async with self._postgres.session() as session:
            overrides = await RebuildJobApi.chunk_overrides(session, collection_id)
        payloads = {
            str(chunk_id): {ENABLED_KEY: override} for chunk_id, _role, override in overrides
        }
        if payloads:
            await QdrantIndexApi.set_payload(self._qdrant.raw, name, payloads)
        return len(payloads)

    async def _purge_vanished(self, collection_id: uuid.UUID, name: str, copied: set[str]) -> int:
        """Delete the points of every copied document Postgres no longer has."""
        async with self._postgres.session() as session:
            alive = {
                str(document_id)
                for document_id in await RebuildJobApi.document_ids(session, collection_id)
            }
        vanished = [uuid.UUID(document_id) for document_id in sorted(copied - alive)]
        if vanished:
            await QdrantIndexApi.delete_by_documents(self._qdrant.raw, name, vanished)
        return len(vanished)

    async def _derive_flag(
        self, collection_id: uuid.UUID, vectors_missing: bool, sparse_reencoded: bool
    ) -> tuple[bool, bool]:
        """
        Derive ``needs_reindex`` per AXIS of the content vectors' embed space.

        A rebuild copies dense vectors (never re-embeds them) but may have re-encoded the content
        sparse vector through the configured provider. The flag clears — and the indexed baselines
        advance to the current config — only when nothing is missing or unfilled, the dense half is
        the one indexed (or the config has no dense slot), and the sparse half is too or was just
        re-encoded (or the config has no sparse slot). A changed dense half raises it (reingest).
        An unknown baseline (never stamped) keeps the stored flag.

        Args:
            collection_id (uuid.UUID): The rebuilt collection.
            vectors_missing (bool): A declared-but-missing vector, or a chunk-scope vector no point
                carries (reingest required) — either keeps the flag raised.
            sparse_reencoded (bool): The copy re-encoded the content sparse vector.

        Returns:
            tuple[bool, bool]: (the flag, whether the dense embed space changed since indexing).
        """
        async with self._postgres.session() as session:
            collection = await CollectionApi.get(session, collection_id)
            if collection is None:
                return False, False
            if vectors_missing:
                await CollectionApi.update(session, collection_id, needs_reindex=True)
                return True, False
            stored, pipeline = collection.indexed_embed_signature, collection.pipeline or {}
            if not stored:
                return bool(collection.needs_reindex), False
            layout = EmbedBlobResolver.layout(pipeline)
            if layout.dense and not EmbedBaseline.dense_matches(stored, pipeline):
                await CollectionApi.update(session, collection_id, needs_reindex=True)
                return True, True
            sparse_ok = (
                not layout.sparse
                or sparse_reencoded
                or EmbedBaseline.sparse_matches(stored, pipeline)
            )
            if not sparse_ok:
                return bool(collection.needs_reindex), False
            schema = await CollectionApi.get_schema(session, collection_id)
            await CollectionApi.update(
                session,
                collection_id,
                indexed_signature=CollectionIndexSignature.compute(pipeline, schema),
                indexed_embed_signature=CollectionIndexSignature.embed_signature(pipeline),
                needs_reindex=False,
            )
            return False, False

    async def reconcile(
        self, collection_id: uuid.UUID, copy: StoreCopyResult
    ) -> RebuildReconcileResult:
        """
        Converge the new store with Postgres after the swap, then derive ``needs_reindex``.

        Args:
            collection_id (uuid.UUID): The rebuilt collection.
            copy (StoreCopyResult): The copy summary (documents seen, vectors carried).

        Returns:
            RebuildReconcileResult: Overrides applied, documents purged, missing vectors, flag.
        """
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        result = RebuildReconcileResult()
        # 1. Chunk enabled overrides (a toggle during the copy landed on the old store).
        result.overrides_applied = await self._apply_overrides(collection_id, name)
        # 2. Documents deleted during the copy: their points were copied, purge them.
        result.removed_documents = await self._purge_vanished(
            collection_id, name, copy.document_ids
        )
        # 3. Honest flag: missing vectors or unfillable chunk vectors keep it raised; otherwise clear
        #    only on an unchanged dense space and a sparse space unchanged or just re-encoded.
        missing = await self._index_state.missing(collection_id)
        result.missing_vectors = [vector for _, vector in missing]
        result.reingest_required_fields = await self._unfilled_chunk_fields(collection_id, copy)
        result.needs_reindex, result.dense_space_changed = await self._derive_flag(
            collection_id,
            bool(missing) or bool(result.reingest_required_fields),
            copy.sparse_reencoded or copy.reencoded_sparse_points > 0,
        )
        return result


__all__ = ["IndexRebuildReconciler"]

# ====== Code Summary ======
# IndexRebuildReconciler — the post-swap RECONCILIATION of a rebuild_index job: re-apply chunk enabled
# overrides, purge points of documents deleted during the copy, then derive needs_reindex honestly — a
# chunk-scope semantic vector no point carries keeps it raised: only a reingest can fill it.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldScope
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

    async def _derive_flag(self, collection_id: uuid.UUID, vectors_missing: bool) -> bool:
        """
        Clear ``needs_reindex`` only when nothing is missing or unfilled AND the content vectors'
        embed space is the one they were indexed under (a rebuild copies content, never re-embeds it).

        Args:
            collection_id (uuid.UUID): The rebuilt collection.
            vectors_missing (bool): A declared-but-missing vector, or a chunk-scope vector no point
                carries (reingest required) — either keeps the flag raised.
        """
        async with self._postgres.session() as session:
            collection = await CollectionApi.get(session, collection_id)
            if collection is None:
                return False
            if vectors_missing:
                await CollectionApi.update(session, collection_id, needs_reindex=True)
                return True
            embed = CollectionIndexSignature.embed_signature(collection.pipeline)
            if collection.indexed_embed_signature != embed:
                return bool(collection.needs_reindex)
            schema = await CollectionApi.get_schema(session, collection_id)
            await CollectionApi.update(
                session,
                collection_id,
                indexed_signature=CollectionIndexSignature.compute(collection.pipeline, schema),
                needs_reindex=False,
            )
            return False

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
        #    only on an unchanged embed space.
        missing = await self._index_state.missing(collection_id)
        result.missing_vectors = [vector for _, vector in missing]
        result.reingest_required_fields = await self._unfilled_chunk_fields(collection_id, copy)
        result.needs_reindex = await self._derive_flag(
            collection_id, bool(missing) or bool(result.reingest_required_fields)
        )
        return result


__all__ = ["IndexRebuildReconciler"]

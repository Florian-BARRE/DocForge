# ====== Code Summary ======
# IndexRebuildFacade — the Postgres side of the rebuild_index job: ADMISSION (collection row FOR
# UPDATE → refuse a 2nd rebuild / an unsupported (legacy chunk-scope lexical) schema / a busy
# collection → insert the document-less job; the partial unique index
# uq_job_active_rebuild_per_collection is the race backstop), the worker's bounded wait for the jobs
# that were live when it started, and the post-swap RECONCILIATION (re-apply chunk enabled overrides,
# purge points of documents deleted during the copy, then derive needs_reindex honestly — a chunk-scope
# semantic vector no point carries keeps it raised: only a reingest can fill it).

# ====== Standard Library Imports ======
import asyncio
import time
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldScope
from shared_libs.services.db.index_signature import CollectionIndexSignature
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import CollectionApi, JobApi, RebuildJobApi
from shared_libs.services.db.postgresql.tables import Job, JobKind, JobStatus
from shared_libs.services.db.qdrant import ENABLED_KEY, QdrantClient, QdrantIndexApi, VectorNames

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers
from .index_rebuild_payloads import (
    AbortProbe,
    CollectionBusyError,
    IndexRebuildActiveError,
    RebuildCancelledError,
    RebuildReconcileResult,
    RebuildUnsupportedError,
    StoreCopyResult,
)
from .index_state_facade import IndexStateFacade

# The partial unique index a concurrent second rebuild admission violates.
_ACTIVE_REBUILD_INDEX = "uq_job_active_rebuild_per_collection"


class IndexRebuildFacade(LoggerClass):
    """Admission, wait and post-swap reconciliation of a collection's index rebuild."""

    def __init__(
        self, postgres: PostgresClient, qdrant: QdrantClient, index_state: IndexStateFacade
    ) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth (jobs, overrides, baseline).
            qdrant (QdrantClient): The vector store (override + orphan reconciliation writes).
            index_state (IndexStateFacade): The declared-vs-needed view (post-swap re-check).
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant
        self._index_state = index_state

    async def active_rebuild(self, collection_id: uuid.UUID) -> Job | None:
        """Return the collection's live rebuild job (unlocked read — the API's fast pre-check)."""
        async with self._postgres.session() as session:
            return await RebuildJobApi.active_rebuild(session, collection_id)

    async def admit(self, collection_id: uuid.UUID) -> uuid.UUID:
        """
        Mint a PENDING rebuild_index job, serialised on the collection row.

        Raises:
            IndexRebuildActiveError: A rebuild is already pending/running.
            RebuildUnsupportedError: The schema has (legacy) chunk-scope lexical fields.
            CollectionBusyError: Other jobs are live on the collection.
            LookupError: The collection does not exist.

        Returns:
            uuid.UUID: The new job id.
        """
        async with self._postgres.session() as session:
            # 1. FOR UPDATE: conflicts with every ingest admission's FOR SHARE.
            if not await RebuildJobApi.lock_collection(session, collection_id, exclusive=True):
                raise LookupError(f"Collection {collection_id} not found.")
            # 2. One rebuild at a time, and never over live work.
            active = await RebuildJobApi.active_rebuild(session, collection_id)
            if active is not None:
                raise IndexRebuildActiveError(collection_id, active.id)
            await self._assert_supported(session, collection_id)
            busy = await RebuildJobApi.active_job_ids(session, collection_id)
            if busy:
                raise CollectionBusyError(collection_id, busy)
            # 3. Insert; the partial unique index is the backstop for a path that skipped the lock.
            job = Job(
                document_id=None,
                collection_id=collection_id,
                kind=JobKind.REBUILD_INDEX,
                status=JobStatus.PENDING,
            )
            try:
                await JobApi.create(session, job)
            except IntegrityError as error:
                if _ACTIVE_REBUILD_INDEX not in str(error.orig):
                    raise
                raise IndexRebuildActiveError(collection_id, None) from error
            return job.id

    async def wait_for_idle(
        self,
        collection_id: uuid.UUID,
        job_id: uuid.UUID,
        timeout_s: float,
        poll_s: float = 2.0,
        should_abort: AbortProbe | None = None,
    ) -> None:
        """
        Wait until no OTHER job is live on the collection (bounded).

        Raises:
            TimeoutError: Jobs are still live after ``timeout_s`` (nothing was touched yet).
            RebuildCancelledError: The rebuild's own row asked to stop while waiting.
        """
        deadline = time.monotonic() + timeout_s
        while True:
            if should_abort is not None and await should_abort():
                raise RebuildCancelledError("rebuild cancelled while waiting for live jobs")
            # 1. Re-read the live set (admission refuses new ingests, so it only shrinks).
            async with self._postgres.session() as session:
                busy = await RebuildJobApi.active_job_ids(session, collection_id, exclude=job_id)
            if not busy:
                return
            # 2. Give up before any Qdrant work rather than copy a moving store.
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"{len(busy)} job(s) still active on collection {collection_id} after "
                    f"{int(timeout_s)}s — rebuild aborted before touching the index; retry later"
                )
            await asyncio.sleep(poll_s)

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

    async def _assert_supported(self, session: AsyncSession, collection_id: uuid.UUID) -> None:
        """Refuse a schema with chunk-scope LEXICAL fields (their vectors would be dropped for good).

        The copy drops every ``meta_*_bm25`` vector and the backfill refills DOCUMENT-scope ones
        only; new chunk-scope lexical fields are already rejected (422) at schema validation, so this
        only ever bites legacy collections.
        """
        schema = await CollectionApi.get_schema(session, collection_id)
        fields = sorted(f.field_name for f in schema if f.scope == FieldScope.CHUNK and f.lexical)
        if fields:
            raise RebuildUnsupportedError(collection_id, fields)

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


__all__ = ["IndexRebuildFacade"]

# ====== Code Summary ======
# IndexRebuildAdmission — the Postgres admission side of the rebuild_index job: collection row FOR
# UPDATE → refuse a 2nd rebuild / an unsupported (legacy chunk-scope lexical) schema / a busy
# collection → insert the document-less job (the partial unique index
# uq_job_active_rebuild_per_collection is the race backstop), plus the worker's bounded wait for the
# jobs that were live when it started.

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
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import CollectionApi, JobApi, RebuildJobApi
from shared_libs.services.db.postgresql.tables import Job, JobKind, JobStatus

# ====== Local Project Imports ======
from .index_rebuild_payloads import (
    AbortProbe,
    CollectionBusyError,
    IndexRebuildActiveError,
    RebuildCancelledError,
    RebuildUnsupportedError,
)

# The partial unique index a concurrent second rebuild admission violates.
_ACTIVE_REBUILD_INDEX = "uq_job_active_rebuild_per_collection"


class IndexRebuildAdmission(LoggerClass):
    """Admission (serialised on the collection row) and pre-copy idle wait of an index rebuild."""

    def __init__(self, postgres: PostgresClient) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth (collection row lock, jobs, schema).
        """
        LoggerClass.__init__(self)
        self._postgres = postgres

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


__all__ = ["IndexRebuildAdmission"]

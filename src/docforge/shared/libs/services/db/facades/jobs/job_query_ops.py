# ====== Code Summary ======
# JobQueryOps — the read side of the jobs façade: job lookups, paged listings, triage counts, the
# dashboard roll-ups (failures, time series, queue depth, cost) and the stage-event / heartbeat
# reads. Each call runs in its own session and never writes. Internal collaborator of JobsFacade.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence
from datetime import datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import JobApi
from shared_libs.services.db.postgresql.apis.job_api import (
    FailureAggregates,
    JobWithNames,
    TimeseriesAggregates,
)
from shared_libs.services.db.postgresql.tables import (
    Job,
    JobStageEvent,
    JobStatus,
    WorkerHeartbeat,
)


class JobQueryOps(LoggerClass):
    """Read-only job queries, each call in its own session."""

    def __init__(self, postgres: PostgresClient) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres

    async def get(self, job_id: uuid.UUID) -> Job | None:
        """Fetch a job by id."""
        async with self._postgres.session() as session:
            return await JobApi.get(session, job_id)

    async def get_with_names(self, job_id: uuid.UUID) -> JobWithNames | None:
        """Fetch a job joined to its document filename + collection name (the monitoring view)."""
        async with self._postgres.session() as session:
            return await JobApi.get_with_names(session, job_id)

    async def get_latest_for_document(self, document_id: uuid.UUID) -> Job | None:
        """The most recent ingestion job for a document — its last run (any status)."""
        async with self._postgres.session() as session:
            return await JobApi.get_latest_for_document(session, document_id)

    async def get_latest_successful_for_document(self, document_id: uuid.UUID) -> Job | None:
        """The most recent DONE job for a document — the run that produced its current persisted IR."""
        async with self._postgres.session() as session:
            return await JobApi.get_latest_successful_for_document(session, document_id)

    async def list_for_collection(self, collection_id: uuid.UUID) -> list[Job]:
        """Return a collection's jobs, newest first."""
        async with self._postgres.session() as session:
            return await JobApi.list_for_collection(session, collection_id)

    async def list_for_collection_with_names(
        self, collection_id: uuid.UUID, limit: int | None = None, offset: int = 0
    ) -> list[JobWithNames]:
        """Return a collection's jobs (newest first, one page), each joined to its display names."""
        async with self._postgres.session() as session:
            return await JobApi.list_for_collection_with_names(
                session, collection_id, limit, offset
            )

    async def count_for_collection(self, collection_id: uuid.UUID) -> int:
        """Count a collection's jobs — the pager's total (independent of limit/offset)."""
        async with self._postgres.session() as session:
            return await JobApi.count_for_collection(session, collection_id)

    async def list_jobs_with_names(
        self,
        collection_id: uuid.UUID | None = None,
        statuses: Sequence[JobStatus] | None = None,
        limit: int | None = None,
        offset: int = 0,
        newest_first: bool = True,
        *,
        sort_by: str = "created",
        stage: str | None = None,
        error_type: str | None = None,
        search: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list[JobWithNames]:
        """Return one bounded page of jobs (fleet-wide or scoped, fully triageable), joined to names."""
        async with self._postgres.session() as session:
            return await JobApi.list_with_names(
                session,
                collection_id=collection_id,
                statuses=statuses,
                limit=limit,
                offset=offset,
                newest_first=newest_first,
                sort_by=sort_by,
                stage=stage,
                error_type=error_type,
                search=search,
                created_after=created_after,
                created_before=created_before,
            )

    async def count_jobs(
        self,
        collection_id: uuid.UUID | None = None,
        statuses: Sequence[JobStatus] | None = None,
        *,
        stage: str | None = None,
        error_type: str | None = None,
        search: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> int:
        """Count jobs matching the same triage filter set — the 'All Jobs' pager total."""
        async with self._postgres.session() as session:
            return await JobApi.count_jobs(
                session,
                collection_id=collection_id,
                statuses=statuses,
                stage=stage,
                error_type=error_type,
                search=search,
                created_after=created_after,
                created_before=created_before,
            )

    async def failure_breakdown(
        self,
        since: datetime,
        collection_id: uuid.UUID | None = None,
        top_n: int = 25,
    ) -> FailureAggregates:
        """Roll up FAILED jobs over a window by cause / stage / collection — the failure-breakdown panel."""
        async with self._postgres.session() as session:
            return await JobApi.failure_breakdown(session, since, collection_id, top_n)

    async def count_failed_since(
        self, since: datetime, collection_id: uuid.UUID | None = None
    ) -> tuple[int, datetime | None]:
        """Count (and date) jobs that failed after a cursor — the 'X new failures since' signal."""
        async with self._postgres.session() as session:
            return await JobApi.count_failed_since(session, since, collection_id)

    async def list_failed_since(
        self, since: datetime, collection_id: uuid.UUID | None = None, limit: int = 50
    ) -> list[uuid.UUID]:
        """Return the ids of jobs that failed after a cursor, newest first (bounded)."""
        async with self._postgres.session() as session:
            return await JobApi.list_failed_since(session, since, collection_id, limit)

    async def job_timeseries(
        self, since: datetime, collection_id: uuid.UUID | None = None
    ) -> TimeseriesAggregates:
        """Return the per-hour arrival/completion counts + backlog baseline — the trends sparklines."""
        async with self._postgres.session() as session:
            return await JobApi.job_timeseries(session, since, collection_id)

    async def list_active_with_names(self) -> list[JobWithNames]:
        """Return every RUNNING job joined to its display names — the fleet activity view."""
        async with self._postgres.session() as session:
            return await JobApi.list_active_with_names(session)

    async def last_successful_ingest_at(self, collection_id: uuid.UUID) -> datetime | None:
        """Return the finish time of the collection's most recent DONE ingest, or None."""
        async with self._postgres.session() as session:
            return await JobApi.last_successful_ingest_at(session, collection_id)

    async def last_successful_ingest_at_by_collections(
        self, collection_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, datetime]:
        """Each collection's last successful ingest in ONE grouped query — the fleet last-ingest."""
        async with self._postgres.session() as session:
            return await JobApi.last_successful_ingest_at_by_collections(session, collection_ids)

    async def list_events(
        self,
        job_id: uuid.UUID,
        include_summaries: bool = True,
        after_created_at: datetime | None = None,
    ) -> list[JobStageEvent]:
        """Return a job's per-node trace, in execution order.

        ``include_summaries=False`` DEFERS the wide JSONB shape summaries out of the SELECT for the
        high-frequency poll path (the live SSE stream). The deferred attributes must not be read off
        the returned rows — the caller pairs it with ``JobEvent.from_row(..., include_summaries=False)``.

        ``after_created_at`` is the SSE stream's incremental delta cursor: when set, only rows inserted
        since that ``created_at`` are read (each poll fetches the new rows, never the whole timeline);
        None reads everything (the one-shot trace read and a fresh stream open).
        """
        async with self._postgres.session() as session:
            return await JobApi.list_events(session, job_id, include_summaries, after_created_at)

    async def list_active(self) -> list[Job]:
        """Return every RUNNING job — the workers' live activity."""
        async with self._postgres.session() as session:
            return await JobApi.list_active(session)

    async def list_heartbeats(self) -> list[WorkerHeartbeat]:
        """Return every worker heartbeat row — the fleet's liveness snapshot (idle-alive included)."""
        async with self._postgres.session() as session:
            return await JobApi.list_heartbeats(session)

    async def queue_depth(self, collection_id: uuid.UUID | None = None) -> tuple[int, int]:
        """Count (pending, running) jobs — fleet-wide when collection_id is None, else scoped."""
        async with self._postgres.session() as session:
            return await JobApi.queue_depth(session, collection_id)

    async def status_counts(self) -> dict[JobStatus, int]:
        """Return the fleet-wide job count per status — the /metrics state gauges (one grouped read)."""
        async with self._postgres.session() as session:
            return await JobApi.status_counts(session)

    async def avg_stage_durations(self, collection_id: uuid.UUID) -> dict[str, float]:
        """Average per-stage duration (seconds) over the collection's DONE jobs — the ETA basis."""
        async with self._postgres.session() as session:
            return await JobApi.avg_stage_durations(session, collection_id)

    async def collection_cost(self, collection_id: uuid.UUID) -> tuple[int, int, float, int]:
        """Roll up the collection's per-document meters: (prompt, completion, usd, doc count)."""
        async with self._postgres.session() as session:
            return await JobApi.collection_cost(session, collection_id)

    async def is_cancel_requested(self, job_id: uuid.UUID) -> bool:
        """Cheap read of a job's cancel flag — the worker's between-stages cancellation probe."""
        async with self._postgres.session() as session:
            return await JobApi.is_cancel_requested(session, job_id)

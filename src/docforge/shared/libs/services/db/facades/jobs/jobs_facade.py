# ====== Code Summary ======
# JobsFacade — the ingestion-observability surface (job lifecycle, stage-event timeline, dashboard
# queries, reaper), each call in its own transaction. A thin orchestrator: every public method
# delegates to JobQueryOps (reads), JobLifecycleOps (writes) or JobReaperOps (force-termination);
# the public names and signatures are the contract callers rely on. Pure Postgres, via JobApi.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis.job_api import (
    FailureAggregates,
    JobWithNames,
    TimeseriesAggregates,
)
from shared_libs.services.db.postgresql.tables import (
    DocumentStatus,
    Job,
    JobStageEvent,
    JobStatus,
    WorkerHeartbeat,
)
from shared_libs.services.db.trace import TraceRefs

# ====== Local Project Imports ======
from .job_lifecycle_ops import JobLifecycleOps
from .job_query_ops import JobQueryOps
from .job_reaper_ops import JobReaperOps


class JobsFacade(LoggerClass):
    """Job lifecycle + stage timeline, each call in its own transaction (delegates to the ops)."""

    def __init__(self, postgres: PostgresClient) -> None:
        LoggerClass.__init__(self)
        self._queries = JobQueryOps(postgres)
        self._lifecycle = JobLifecycleOps(postgres)
        self._reaper = JobReaperOps(postgres)

    # ---------------------- Reads (JobQueryOps) ---------------------- #
    async def get(self, job_id: uuid.UUID) -> Job | None:
        """Fetch a job by id."""
        return await self._queries.get(job_id)

    async def get_with_names(self, job_id: uuid.UUID) -> JobWithNames | None:
        """Fetch a job joined to its document filename + collection name (the monitoring view)."""
        return await self._queries.get_with_names(job_id)

    async def get_latest_for_document(self, document_id: uuid.UUID) -> Job | None:
        """The most recent ingestion job for a document — its last run (any status)."""
        return await self._queries.get_latest_for_document(document_id)

    async def get_latest_successful_for_document(self, document_id: uuid.UUID) -> Job | None:
        """The most recent DONE job for a document — the run that produced its current persisted IR."""
        return await self._queries.get_latest_successful_for_document(document_id)

    async def list_for_collection(self, collection_id: uuid.UUID) -> list[Job]:
        """Return a collection's jobs, newest first."""
        return await self._queries.list_for_collection(collection_id)

    async def list_for_collection_with_names(
        self, collection_id: uuid.UUID, limit: int | None = None, offset: int = 0
    ) -> list[JobWithNames]:
        """Return a collection's jobs (newest first, one page), each joined to its display names."""
        return await self._queries.list_for_collection_with_names(collection_id, limit, offset)

    async def count_for_collection(self, collection_id: uuid.UUID) -> int:
        """Count a collection's jobs — the pager's total (independent of limit/offset)."""
        return await self._queries.count_for_collection(collection_id)

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
        return await self._queries.list_jobs_with_names(
            collection_id,
            statuses,
            limit,
            offset,
            newest_first,
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
        return await self._queries.count_jobs(
            collection_id,
            statuses,
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
        return await self._queries.failure_breakdown(since, collection_id, top_n)

    async def count_failed_since(
        self, since: datetime, collection_id: uuid.UUID | None = None
    ) -> tuple[int, datetime | None]:
        """Count (and date) jobs that failed after a cursor — the 'X new failures since' signal."""
        return await self._queries.count_failed_since(since, collection_id)

    async def list_failed_since(
        self, since: datetime, collection_id: uuid.UUID | None = None, limit: int = 50
    ) -> list[uuid.UUID]:
        """Return the ids of jobs that failed after a cursor, newest first (bounded)."""
        return await self._queries.list_failed_since(since, collection_id, limit)

    async def job_timeseries(
        self, since: datetime, collection_id: uuid.UUID | None = None
    ) -> TimeseriesAggregates:
        """Return the per-hour arrival/completion counts + backlog baseline — the trends sparklines."""
        return await self._queries.job_timeseries(since, collection_id)

    async def list_active_with_names(self) -> list[JobWithNames]:
        """Return every RUNNING job joined to its display names — the fleet activity view."""
        return await self._queries.list_active_with_names()

    async def last_successful_ingest_at(self, collection_id: uuid.UUID) -> datetime | None:
        """Return the finish time of the collection's most recent DONE ingest, or None."""
        return await self._queries.last_successful_ingest_at(collection_id)

    async def last_successful_ingest_at_by_collections(
        self, collection_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, datetime]:
        """Each collection's last successful ingest in ONE grouped query — the fleet last-ingest."""
        return await self._queries.last_successful_ingest_at_by_collections(collection_ids)

    async def list_events(
        self,
        job_id: uuid.UUID,
        include_summaries: bool = True,
        after_created_at: datetime | None = None,
    ) -> list[JobStageEvent]:
        """Return a job's per-node trace, in execution order (see ``JobQueryOps.list_events``)."""
        return await self._queries.list_events(job_id, include_summaries, after_created_at)

    async def list_active(self) -> list[Job]:
        """Return every RUNNING job — the workers' live activity."""
        return await self._queries.list_active()

    async def list_heartbeats(self) -> list[WorkerHeartbeat]:
        """Return every worker heartbeat row — the fleet's liveness snapshot (idle-alive included)."""
        return await self._queries.list_heartbeats()

    async def queue_depth(self, collection_id: uuid.UUID | None = None) -> tuple[int, int]:
        """Count (pending, running) jobs — fleet-wide when collection_id is None, else scoped."""
        return await self._queries.queue_depth(collection_id)

    async def status_counts(self) -> dict[JobStatus, int]:
        """Return the fleet-wide job count per status — the /metrics state gauges (one grouped read)."""
        return await self._queries.status_counts()

    async def avg_stage_durations(self, collection_id: uuid.UUID) -> dict[str, float]:
        """Average per-stage duration (seconds) over the collection's DONE jobs — the ETA basis."""
        return await self._queries.avg_stage_durations(collection_id)

    async def collection_cost(self, collection_id: uuid.UUID) -> tuple[int, int, float, int]:
        """Roll up the collection's per-document meters: (prompt, completion, usd, doc count)."""
        return await self._queries.collection_cost(collection_id)

    async def is_cancel_requested(self, job_id: uuid.UUID) -> bool:
        """Cheap read of a job's cancel flag — the worker's between-stages cancellation probe."""
        return await self._queries.is_cancel_requested(job_id)

    # ---------------------- Lifecycle, timeline, heartbeats (JobLifecycleOps) ---------------------- #
    async def create_metadata_sync(
        self, document_id: uuid.UUID, collection_id: uuid.UUID
    ) -> uuid.UUID:
        """Pre-create a tracked ``metadata_sync`` job row (QUEUED) for a per-document value edit."""
        return await self._lifecycle.create_metadata_sync(document_id, collection_id)

    async def mark_running(
        self, job_id: uuid.UUID, worker_id: str, attempt: int, started_at: datetime
    ) -> None:
        """Claim the job for a worker (retry-safe: clears the previous attempt's outcome)."""
        await self._lifecycle.mark_running(job_id, worker_id, attempt, started_at)

    async def set_progress(self, job_id: uuid.UUID, current_stage: str, progress: int) -> None:
        """Report the current stage and coarse progress."""
        await self._lifecycle.set_progress(job_id, current_stage, progress)

    async def set_items(
        self, job_id: uuid.UUID, items_done: int | None, items_total: int | None
    ) -> None:
        """Set the fan-out per-item counter (both None = reset when leaving a fan-out stage)."""
        await self._lifecycle.set_items(job_id, items_done, items_total)

    async def mark_done(self, job_id: uuid.UUID, finished_at: datetime) -> None:
        """Complete the job successfully."""
        await self._lifecycle.mark_done(job_id, finished_at)

    async def mark_failed(
        self,
        job_id: uuid.UUID,
        error: str,
        finished_at: datetime,
        failed_node_id: str | None = None,
        failed_node_kind: str | None = None,
        failed_item_index: int | None = None,
        error_type: str | None = None,
    ) -> None:
        """Fail the job with its error message + structured breadcrumb; close its open stage row."""
        await self._lifecycle.mark_failed(
            job_id,
            error,
            finished_at,
            failed_node_id=failed_node_id,
            failed_node_kind=failed_node_kind,
            failed_item_index=failed_item_index,
            error_type=error_type,
        )

    async def request_cancel(self, job_id: uuid.UUID) -> Job | None:
        """Raise a running job's cooperative-cancel flag (honoured at its next stage boundary)."""
        return await self._lifecycle.request_cancel(job_id)

    async def persist_execution_tree(
        self,
        job_id: uuid.UUID,
        record: NodeExecutionRecord,
        refs: dict[str, TraceRefs] | None = None,
    ) -> None:
        """Persist the run's FULL per-node execution tree onto the job's stage timeline."""
        await self._lifecycle.persist_execution_tree(job_id, record, refs)

    async def record_event(self, event: JobStageEvent) -> JobStageEvent:
        """Append a stage event to the job's timeline (returns it with its id assigned)."""
        return await self._lifecycle.record_event(event)

    async def finalize_event(
        self,
        event_id: uuid.UUID,
        status: str,
        finished_at: datetime,
        detail: str | None,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        cost_usd: Decimal | None,
    ) -> None:
        """Close an open stage-event row (opened at START) with its final outcome/usage."""
        await self._lifecycle.finalize_event(
            event_id,
            status,
            finished_at,
            detail,
            prompt_tokens,
            completion_tokens,
            cost_usd,
        )

    async def add_usage(
        self,
        job_id: uuid.UUID,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float | None,
    ) -> None:
        """Fold a stage's token/cost usage into the job's per-document running totals (null-safe)."""
        await self._lifecycle.add_usage(job_id, prompt_tokens, completion_tokens, cost_usd)

    async def upsert_heartbeat(
        self,
        worker_id: str,
        worker_name: str,
        last_seen: datetime,
        started_at: datetime,
        max_jobs: int | None = None,
        cpu_percent: float | None = None,
        mem_mb: float | None = None,
        mem_percent: float | None = None,
    ) -> None:
        """Register/refresh a worker's liveness heartbeat row (idle-but-alive visibility + capacity + resources)."""
        await self._lifecycle.upsert_heartbeat(
            worker_id,
            worker_name,
            last_seen,
            started_at,
            max_jobs,
            cpu_percent,
            mem_mb,
            mem_percent,
        )

    async def delete_heartbeat(self, worker_id: str) -> None:
        """De-register a worker on clean shutdown — its heartbeat row vanishes immediately."""
        await self._lifecycle.delete_heartbeat(worker_id)

    async def prune_stale_heartbeats(self, older_than_seconds: float) -> list[str]:
        """Delete heartbeat rows frozen past the cutoff (crashed workers); return the removed ids."""
        return await self._lifecycle.prune_stale_heartbeats(older_than_seconds)

    async def prune_history(self, cutoff: datetime) -> int:
        """Delete terminal jobs (and their stage-events) older than ``cutoff`` — the retention sweep."""
        return await self._lifecycle.prune_history(cutoff)

    # ---------------------- Force-termination and reaping (JobReaperOps) ---------------------- #
    async def abandon(self, job_id: uuid.UUID, reason: str) -> None:
        """Fail a just-created side-job WITHOUT touching its document — frees the active-job lock."""
        await self._reaper.abandon(job_id, reason)

    async def abandon_ingest(self, job_id: uuid.UUID, reason: str) -> None:
        """Fail a just-admitted INGEST job whose enqueue then failed — frees the lock AND fails the doc."""
        await self._reaper.abandon_ingest(job_id, reason)

    async def _terminate(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        *,
        job_status: JobStatus,
        doc_status: DocumentStatus,
        reason: str,
        error_type: str | None = None,
    ) -> Job | None:
        """Transition ONE job to a terminal status inside the caller's session (see ``JobReaperOps.terminate``)."""
        return await self._reaper.terminate(
            session,
            job_id,
            job_status=job_status,
            doc_status=doc_status,
            reason=reason,
            error_type=error_type,
        )

    async def force_terminate(self, job_id: uuid.UUID, reason: str) -> Job | None:
        """Immediately CANCEL a job and its document, regardless of worker state — the manual reaper."""
        return await self._reaper.force_terminate(job_id, reason)

    async def reap_stale(
        self, older_than_seconds: float, heartbeat_stale_seconds: float
    ) -> list[uuid.UUID]:
        """Fail every RUNNING job silent past the threshold WHOSE WORKER IS ALSO GONE — orphan recovery."""
        return await self._reaper.reap_stale(older_than_seconds, heartbeat_stale_seconds)

    async def reap_over_job_timeout(
        self,
        default_job_timeout_seconds: float,
        grace_seconds: float,
        heartbeat_stale_seconds: float,
        rebuild_job_timeout_seconds: float | None = None,
    ) -> list[uuid.UUID]:
        """Fail every RUNNING job on a LIVE worker whose age blew past its own job timeout — the watchdog."""
        return await self._reaper.reap_over_job_timeout(
            default_job_timeout_seconds,
            grace_seconds,
            heartbeat_stale_seconds,
            rebuild_job_timeout_seconds,
        )

    async def reclaim_worker_jobs(self, worker_id: str) -> list[uuid.UUID]:
        """Fail this worker id's own leftover RUNNING jobs — SAME-HOSTNAME restart hygiene only."""
        return await self._reaper.reclaim_worker_jobs(worker_id)


__all__ = ["JobsFacade"]

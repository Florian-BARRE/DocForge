# ====== Code Summary ======
# JobLifecycleOps — the write side the worker drives: the pre-created side-job row, the lifecycle
# transitions (running / progress / items / done / failed), the cancel flag, the stage-event
# timeline writes, the usage meters, the worker heartbeats and the history retention sweep. Each
# call runs in its own small transaction. Internal collaborator of JobsFacade.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from decimal import Decimal

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import JobApi
from shared_libs.services.db.postgresql.apis.execution_tree import TraceRefs
from shared_libs.services.db.postgresql.tables import Job, JobKind, JobStageEvent, JobStatus


class JobLifecycleOps(LoggerClass):
    """Job lifecycle + timeline + heartbeat writes, each call in its own transaction."""

    def __init__(self, postgres: PostgresClient) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres

    async def create_metadata_sync(
        self, document_id: uuid.UUID, collection_id: uuid.UUID
    ) -> uuid.UUID:
        """
        Pre-create a tracked ``metadata_sync`` job row (QUEUED) for a per-document value edit.

        The metadata value-edit path mirrors ingestion's "the caller mints the job row, the worker
        drives its lifecycle" contract: the row exists BEFORE the task is enqueued, so the id handed
        back to the client is immediately retrievable via ``GET /jobs/{id}`` (never a 404). Only the
        fields a non-ingest side-job needs are set — ``kind=metadata_sync``, the document + collection,
        status PENDING (the "queued" state); the ingest-specific nullable columns stay null. This job
        tracks no pipeline stages, so no stage-event row is opened here.

        NOTE: the ``uq_job_active_per_document`` partial-unique index is kind-agnostic, so this INSERT
        raises if the document already has a live (PENDING/RUNNING) job of ANY kind — which is the
        intended guard (a metadata re-embed must not race a full reingest of the same document). The
        router treats a failure here as best-effort (the value write already committed), so that rare
        conflict surfaces as ``job_id=null``, never a 500.

        Args:
            document_id (uuid.UUID): The document whose metadata is being re-synced.
            collection_id (uuid.UUID): That document's collection.

        Returns:
            uuid.UUID: The freshly-created job row's id (the tracked, pollable id).
        """
        async with self._postgres.session() as session:
            job = Job(
                document_id=document_id,
                collection_id=collection_id,
                kind=JobKind.METADATA_SYNC,
                status=JobStatus.PENDING,
            )
            await JobApi.create(session, job)
            return job.id

    async def mark_running(
        self, job_id: uuid.UUID, worker_id: str, attempt: int, started_at: datetime
    ) -> None:
        """Claim the job for a worker (retry-safe: clears the previous attempt's outcome)."""
        async with self._postgres.session() as session:
            await JobApi.mark_running(session, job_id, worker_id, attempt, started_at)

    async def set_progress(self, job_id: uuid.UUID, current_stage: str, progress: int) -> None:
        """Report the current stage and coarse progress."""
        async with self._postgres.session() as session:
            await JobApi.set_progress(session, job_id, current_stage, progress)

    async def set_items(
        self, job_id: uuid.UUID, items_done: int | None, items_total: int | None
    ) -> None:
        """Set the fan-out per-item counter (both None = reset when leaving a fan-out stage)."""
        async with self._postgres.session() as session:
            await JobApi.set_items(session, job_id, items_done, items_total)

    async def mark_done(self, job_id: uuid.UUID, finished_at: datetime) -> None:
        """Complete the job successfully."""
        async with self._postgres.session() as session:
            await JobApi.mark_done(session, job_id, finished_at)

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
        async with self._postgres.session() as session:
            await JobApi.mark_failed(
                session,
                job_id,
                error,
                finished_at,
                failed_node_id=failed_node_id,
                failed_node_kind=failed_node_kind,
                failed_item_index=failed_item_index,
                error_type=error_type,
            )

    async def request_cancel(self, job_id: uuid.UUID) -> Job | None:
        """
        Raise a running job's cooperative-cancel flag (honoured at its next stage boundary).

        Leaves the job RUNNING — the worker's between-stages guard re-reads the flag and stops
        itself. Returns the flagged job (or None for an unknown id) so the caller reports its state.
        """
        async with self._postgres.session() as session:
            job = await JobApi.request_cancel(session, job_id)
            if job is not None:
                self.logger.info(f"Cancellation requested for running job {job_id}")
            return job

    async def persist_execution_tree(
        self,
        job_id: uuid.UUID,
        record: NodeExecutionRecord,
        refs: dict[str, TraceRefs] | None = None,
    ) -> None:
        """Persist the run's FULL per-node execution tree onto the job's stage timeline.

        Walks the outermost execution record into materialized-path rows and reconciles them with the
        live stage timeline: the open root rows are filled with their tree coordinates + score + trace
        capture, every nested node (group children, per-item ForEach body instances) is inserted. The
        shape summaries ride on the record; the full-payload ``refs`` (object-store keys the worker
        stored beforehand) are stamped when present. Idempotent, so the worker may call it on both the
        success and the empty-chunk-warning paths.
        """
        async with self._postgres.session() as session:
            await JobApi.persist_execution_tree(session, job_id, record, refs=refs)

    async def record_event(self, event: JobStageEvent) -> JobStageEvent:
        """Append a stage event to the job's timeline (returns it with its id assigned)."""
        async with self._postgres.session() as session:
            return await JobApi.record_event(session, event)

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
        async with self._postgres.session() as session:
            await JobApi.finalize_event(
                session,
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
        async with self._postgres.session() as session:
            await JobApi.add_usage(session, job_id, prompt_tokens, completion_tokens, cost_usd)

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
        async with self._postgres.session() as session:
            await JobApi.upsert_heartbeat(
                session,
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
        async with self._postgres.session() as session:
            await JobApi.delete_heartbeat(session, worker_id)

    async def prune_stale_heartbeats(self, older_than_seconds: float) -> list[str]:
        """Delete heartbeat rows frozen past the cutoff (crashed workers); return the removed ids."""
        async with self._postgres.session() as session:
            return await JobApi.prune_stale_heartbeats(session, older_than_seconds)

    async def prune_history(self, cutoff: datetime) -> int:
        """
        Delete terminal jobs (and their stage-events) older than ``cutoff`` — the retention sweep.

        Never touches a pending/running job, and skips any job still carrying an un-GC'd full-trace
        payload so the row prune can never strand an object-store trace namespace (see
        ``JobApi.prune_history``). Runs inside one committed session and logs the count.

        Args:
            cutoff (datetime): Terminal jobs with ``created_at`` strictly before this are removed.

        Returns:
            int: The number of job rows deleted.
        """
        # 1. Age-based bulk delete inside one committed session.
        async with self._postgres.session() as session:
            deleted = await JobApi.prune_history(session, cutoff)
        if deleted:
            self.logger.info(
                f"Job-history retention pruned {deleted} terminal job(s) older than "
                f"{cutoff.isoformat()}"
            )
        return deleted

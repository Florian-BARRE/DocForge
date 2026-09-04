# ====== Code Summary ======
# JobsFacade — the ingestion-observability surface: the job lifecycle transitions (each in its own
# small transaction, as the worker reports them) and the stage-event timeline the live UI reads.
# Pure Postgres; wraps JobApi so callers never manage sessions themselves.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import DocumentApi, JobApi
from shared_libs.services.db.postgresql.apis.job_api import JobWithNames
from shared_libs.services.db.postgresql.tables import (
    DocumentStatus,
    Job,
    JobStageEvent,
    JobStatus,
    WorkerHeartbeat,
)


class JobsFacade(LoggerClass):
    """Job lifecycle + stage timeline, each call in its own transaction."""

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
        """The most recent ingestion job for a document — its last run's stage provenance."""
        async with self._postgres.session() as session:
            return await JobApi.get_latest_for_document(session, document_id)

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

    async def list_events(self, job_id: uuid.UUID) -> list[JobStageEvent]:
        """Return a job's per-node trace, in execution order."""
        async with self._postgres.session() as session:
            return await JobApi.list_events(session, job_id)

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

    async def upsert_heartbeat(
        self, worker_id: str, worker_name: str, last_seen: datetime, started_at: datetime
    ) -> None:
        """Register/refresh a worker's liveness heartbeat row (idle-but-alive visibility)."""
        async with self._postgres.session() as session:
            await JobApi.upsert_heartbeat(session, worker_id, worker_name, last_seen, started_at)

    async def delete_heartbeat(self, worker_id: str) -> None:
        """De-register a worker on clean shutdown — its heartbeat row vanishes immediately."""
        async with self._postgres.session() as session:
            await JobApi.delete_heartbeat(session, worker_id)

    async def prune_stale_heartbeats(self, older_than_seconds: float) -> list[str]:
        """Delete heartbeat rows frozen past the cutoff (crashed workers); return the removed ids."""
        async with self._postgres.session() as session:
            return await JobApi.prune_stale_heartbeats(session, older_than_seconds)

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

    async def avg_stage_durations(self, collection_id: uuid.UUID) -> dict[str, float]:
        """Average per-stage duration (seconds) over the collection's DONE jobs — the ETA basis."""
        async with self._postgres.session() as session:
            return await JobApi.avg_stage_durations(session, collection_id)

    async def collection_cost(self, collection_id: uuid.UUID) -> tuple[int, int, float, int]:
        """Roll up the collection's per-document meters: (prompt, completion, usd, doc count)."""
        async with self._postgres.session() as session:
            return await JobApi.collection_cost(session, collection_id)

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

    async def is_cancel_requested(self, job_id: uuid.UUID) -> bool:
        """Cheap read of a job's cancel flag — the worker's between-stages cancellation probe."""
        async with self._postgres.session() as session:
            return await JobApi.is_cancel_requested(session, job_id)

    async def _terminate(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        *,
        job_status: JobStatus,
        doc_status: DocumentStatus,
        reason: str,
    ) -> Job | None:
        """
        Transition ONE job to a terminal status AND its document to a terminal status, atomically.

        The single force-terminate code path shared by cancel-force and the cron reaper: it marks the
        job terminal (closing its open stage row) via ``JobApi.mark_terminal`` and flags its owning
        document terminal, in the SAME transaction. Session-scoped so the reaper can loop it over many
        stale jobs in one unit of work.

        Args:
            session (AsyncSession): The active DB session (the caller owns the transaction).
            job_id (uuid.UUID): The job to terminate.
            job_status (JobStatus): The job's terminal status (CANCELLED for cancel, FAILED for reap).
            doc_status (DocumentStatus): The document's terminal status to mirror.
            reason (str): The human-readable reason recorded on the job + its open stage row.

        Returns:
            Job | None: The terminated job, or None when the id is unknown.
        """
        job = await JobApi.mark_terminal(
            session, job_id, status=job_status, reason=reason, finished_at=datetime.now(UTC)
        )
        if job is not None and job.document_id is not None:
            # Ownership edge-guard: only mirror the terminal status onto the DOCUMENT when THIS job is
            # still the document's most-recent run. A newer job (a reingest queued while this one
            # wedged, since reingest always mints a fresh job row) OWNS the document state now — an old
            # reaped/cancelled job must never clobber the newer run's terminal/processing state. The
            # job row itself is always terminated (it genuinely is over); only the shared document
            # write is gated. Mirrors ``DocumentApi.finalize_done``'s guard against a racing terminal.
            latest = await JobApi.get_latest_for_document(session, job.document_id)
            if latest is None or latest.id == job_id:
                await DocumentApi.set_status(session, job.document_id, doc_status)
        return job

    async def force_terminate(self, job_id: uuid.UUID, reason: str) -> Job | None:
        """
        Immediately CANCEL a job and its document, regardless of worker state — the manual reaper.

        For a wedged/infinite job (or a queued job cancelled before it runs): marks the job CANCELLED
        and its document CANCELLED now, sharing the reaper's transition semantics via ``_terminate``.
        A still-alive worker also stops cooperatively at its next boundary (mark_terminal raises the
        cancel flag) and can never resurrect the job (mark_done/mark_failed no-op once CANCELLED).

        Args:
            job_id (uuid.UUID): The job to force-terminate.
            reason (str): The recorded human-readable reason.

        Returns:
            Job | None: The terminated job, or None when the id is unknown.
        """
        async with self._postgres.session() as session:
            job = await self._terminate(
                session,
                job_id,
                job_status=JobStatus.CANCELLED,
                doc_status=DocumentStatus.CANCELLED,
                reason=reason,
            )
        if job is not None:
            self.logger.info(f"Force-terminated job {job_id} (CANCELLED): {reason}")
        return job

    async def reap_stale(
        self, older_than_seconds: float, heartbeat_stale_seconds: float
    ) -> list[uuid.UUID]:
        """
        Fail every RUNNING job silent past the threshold WHOSE WORKER IS ALSO GONE — orphan recovery.

        A dev worker hot-reload (or a crash) drops the in-flight arq task, but the DB job row stays
        RUNNING forever and its document PROCESSING. This lists such wedged jobs and, for each, marks
        the job FAILED with an operator-clear reason AND flags its owning document FAILED (so the
        document is visibly re-ingestable) — through the SAME ``_terminate`` path a manual cancel-force
        uses. Crucially, ``list_stale`` now vetoes any job whose worker heartbeat is still fresh, so a
        HEALTHY job running one long silent stage on a live worker is never reaped — only jobs on a
        dead/absent worker qualify. Idempotent under concurrency: a row already reaped no longer
        matches ``status == RUNNING``, so a second pass — or a second worker — is a harmless no-op.

        Args:
            older_than_seconds (float): A RUNNING job silent (no row write) longer than this is a
                candidate — but only if its worker is also gone.
            heartbeat_stale_seconds (float): A worker heartbeat older than this (or absent) is
                presumed dead; a fresher heartbeat vetoes the reap of that worker's jobs.

        Returns:
            list[uuid.UUID]: The reaped job ids (empty when nothing was stale).
        """
        minutes = int(older_than_seconds // 60)
        # The reaper's terminal status is FAILED, so its message must read like a failure — NEVER a
        # "cancelled:" prefix (that belongs to the operator/worker cancel path, which sets CANCELLED).
        error = (
            f"reaped: progress stalled for >{minutes}m beyond the reap window — "
            f"worker unwedged, presumed orphaned by a worker restart"
        )
        reaped: list[uuid.UUID] = []
        async with self._postgres.session() as session:
            for job in await JobApi.list_stale(
                session, older_than_seconds, heartbeat_stale_seconds
            ):
                await self._terminate(
                    session,
                    job.id,
                    job_status=JobStatus.FAILED,
                    doc_status=DocumentStatus.FAILED,
                    reason=error,
                )
                reaped.append(job.id)
        if reaped:
            self.logger.warning(f"Reaped {len(reaped)} stale job(s): {error}")
        return reaped

    async def reclaim_worker_jobs(self, worker_id: str) -> list[uuid.UUID]:
        """
        Fail every RUNNING job still attributed to this worker id — called at the worker's STARTUP.

        A freshly-started worker owns NO in-flight task, so any RUNNING row stamped with its
        ``worker_id`` is a leftover from its previous incarnation (a hot-reload, crash or hard kill
        that never marked the row terminal). Reclaiming them here clears the orphaned "stalled"
        pile-up INSTANTLY on every (re)start — instead of leaving those rows orange until the reaper's
        stale window elapses. Marks each job FAILED and its document FAILED (visibly re-ingestable)
        through the same ``_terminate`` path a manual cancel-force uses. Independent of the reap flag:
        this is startup hygiene, not the periodic reaper.

        Args:
            worker_id (str): The stable id of the worker reclaiming its own orphans.

        Returns:
            list[uuid.UUID]: The reclaimed job ids (empty when the worker had no leftovers).
        """
        error = (
            "reclaimed at worker startup: the previous worker process did not mark this job "
            "terminal (hot-reload/crash) — presumed orphaned, re-ingest to retry"
        )
        reclaimed: list[uuid.UUID] = []
        async with self._postgres.session() as session:
            for job in await JobApi.list_running_for_worker(session, worker_id):
                await self._terminate(
                    session,
                    job.id,
                    job_status=JobStatus.FAILED,
                    doc_status=DocumentStatus.FAILED,
                    reason=error,
                )
                reclaimed.append(job.id)
        if reclaimed:
            self.logger.warning(
                f"Reclaimed {len(reclaimed)} orphaned RUNNING job(s) from worker {worker_id}'s "
                f"previous incarnation at startup."
            )
        return reclaimed


__all__ = ["JobsFacade"]

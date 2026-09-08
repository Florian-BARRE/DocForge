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
from shared_libs.pipelines.base import NodeExecutionRecord
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import DocumentApi, JobApi
from shared_libs.services.db.postgresql.apis.execution_tree import TraceRefs
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
    ) -> list[JobWithNames]:
        """Return one page of jobs (fleet-wide or scoped, optional status filter), joined to names."""
        async with self._postgres.session() as session:
            return await JobApi.list_with_names(
                session,
                collection_id=collection_id,
                statuses=statuses,
                limit=limit,
                offset=offset,
                newest_first=newest_first,
            )

    async def count_jobs(
        self,
        collection_id: uuid.UUID | None = None,
        statuses: Sequence[JobStatus] | None = None,
    ) -> int:
        """Count jobs matching the optional collection + status filter — the 'All Jobs' pager total."""
        async with self._postgres.session() as session:
            return await JobApi.count_jobs(session, collection_id=collection_id, statuses=statuses)

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
        error_type: str | None = None,
    ) -> Job | None:
        """
        Transition ONE job to a terminal status AND its document to a terminal status, atomically.

        The single force-terminate code path shared by cancel-force and the cron reaper: it marks the
        job terminal (closing its open stage row) via ``JobApi.mark_terminal`` and flags its owning
        document terminal, in the SAME transaction. Session-scoped so the reaper can loop it over many
        stale jobs in one unit of work.

        ``mark_terminal`` is a CONDITIONAL transition (it flips only a still-live job and RETURNs it, or
        None when the job already went terminal). A None therefore means a concurrent writer — the
        worker finishing the same job the live-worker watchdog was reaping — already closed it: this
        returns without touching the document, so a fully-ingested document is never flipped to FAILED
        under that race. The document mirror runs ONLY on a winning transition (``job is not None``).

        Args:
            session (AsyncSession): The active DB session (the caller owns the transaction).
            job_id (uuid.UUID): The job to terminate.
            job_status (JobStatus): The job's terminal status (CANCELLED for cancel, FAILED for reap).
            doc_status (DocumentStatus): The document's terminal status to mirror.
            reason (str): The human-readable reason recorded on the job + its open stage row.
            error_type (str | None): The structured failure cause stamped on the job (the reaper's
                ``worker_killed`` / ``job_timeout_exceeded``); None for a plain cancel (no attribution).

        Returns:
            Job | None: The terminated job, or None when the id is unknown.
        """
        job = await JobApi.mark_terminal(
            session,
            job_id,
            status=job_status,
            reason=reason,
            finished_at=datetime.now(UTC),
            error_type=error_type,
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

        A dev worker hot-reload, a crash, a SIGKILL or an OOM-kill drops the in-flight arq task, but
        the DB job row stays RUNNING forever and its document PROCESSING. This lists such wedged jobs
        and, for each, marks the job FAILED with an operator-clear reason AND flags its owning document
        FAILED (so the document is visibly re-ingestable) — through the SAME ``_terminate`` path a
        manual cancel-force uses. Crucially, ``list_stale`` vetoes any job whose worker heartbeat is
        still fresh, so a HEALTHY job running one long silent stage on a live worker is never reaped
        here — only jobs on a dead/absent worker qualify (a live-worker wedge is the sibling
        ``reap_over_job_timeout`` path). Idempotent under concurrency: a row already reaped no longer matches
        ``status == RUNNING``, so a second pass — or a second worker — is a harmless no-op.

        Attribution: because a dead heartbeat means the worker PROCESS is gone, this stamps
        ``error_type = "worker_killed"`` and an OOM-forward reason — a process vanishing under a heavy
        document is most often an out-of-memory kill, and the operator's actionable levers are the same
        regardless of the exact signal. The failure is TERMINAL (never auto-retried: arq's retry is off
        and the reaper marks FAILED), so a killed job never loops back to re-OOM; the document stays
        re-ingestable by the operator.

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
            f"reaped: the worker processing this document was lost — no heartbeat and no progress "
            f"for >{minutes}m (a crash, restart, or an out-of-memory kill), so the job is presumed "
            f"orphaned. If this recurs on heavy documents it is most likely out-of-memory: use the "
            f"light preset, raise the worker's memory limit, or lower WORKER_CONCURRENCY. The "
            f"document is re-ingestable."
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
                    error_type="worker_killed",
                )
                reaped.append(job.id)
        if reaped:
            self.logger.warning(f"Reaped {len(reaped)} killed-worker job(s): {error}")
        return reaped

    async def reap_over_job_timeout(
        self,
        default_job_timeout_seconds: float,
        grace_seconds: float,
        heartbeat_stale_seconds: float,
    ) -> list[uuid.UUID]:
        """
        Fail every RUNNING job on a LIVE worker whose age blew past its own job timeout — the watchdog.

        The second reap condition, independent of the worker heartbeat, that closes ``reap_stale``'s
        blind spot: a worker can be ALIVE (its arq loop heartbeats) while ONE job is dead-wedged (an
        OOM-killed parse thread, a hung native call arq's async cancel cannot kill). Its fresh
        heartbeat VETOes ``reap_stale``, so without this the slot stays wedged until arq's uniform outer
        cap — potentially hours for a short-job-timeout collection. This lists such jobs (age past the
        per-collection effective job timeout + grace, on a fresh-heartbeat worker) and fails each with
        ``error_type = "job_timeout_exceeded"`` and a stage-named reason, flagging its document FAILED
        (re-ingestable) through the SAME ``_terminate`` path.

        The job timeout is the job's REAL per-collection job timeout (``list_over_job_timeout`` reads
        it), and the grace keeps the watchdog conservative — a genuinely long docling parse WITHIN its
        job timeout is never falsely reaped. Terminal, never auto-retried (a wedged stage would just
        wedge again); the operator re-ingests once they have addressed the hang (raise the job timeout,
        simplify the pipeline, or use the light preset). Idempotent: a reaped row no longer matches RUNNING.

        Args:
            default_job_timeout_seconds (float): The global default for a collection with no per-collection
                ``job_timeout_seconds`` (WORKER_JOB_TIMEOUT_SECONDS).
            grace_seconds (float): Margin added on top of the effective job timeout before reaping, so the
                engine's own cancel at the job timeout always gets first chance (WORKER_OVER_JOB_TIMEOUT_GRACE_SECONDS).
            heartbeat_stale_seconds (float): The SAME cutoff ``reap_stale`` uses — a heartbeat within
                it is FRESH (the live worker this path targets), which keeps the two paths disjoint.

        Returns:
            list[uuid.UUID]: The reaped job ids (empty when nothing is over its job timeout).
        """
        reaped: list[uuid.UUID] = []
        async with self._postgres.session() as session:
            for job, job_timeout in await JobApi.list_over_job_timeout(
                session, default_job_timeout_seconds, grace_seconds, heartbeat_stale_seconds
            ):
                stage = job.current_stage or "current stage"
                # FAILED terminal status → the reason must read like a failure, never a "cancelled:"
                # prefix (that belongs to the CANCELLED cancel path).
                error = (
                    f"reaped: this document's '{stage}' stage exceeded its {int(job_timeout)}s job timeout "
                    f"on a live worker (a hung or runaway stage the engine could not cancel). "
                    f"Re-ingest to retry; if it recurs, raise the collection's job_timeout_seconds, "
                    f"use the light preset, or simplify the pipeline."
                )
                await self._terminate(
                    session,
                    job.id,
                    job_status=JobStatus.FAILED,
                    doc_status=DocumentStatus.FAILED,
                    reason=error,
                    error_type="job_timeout_exceeded",
                )
                reaped.append(job.id)
        if reaped:
            self.logger.warning(f"Reaped {len(reaped)} over-job-timeout job(s) on live workers.")
        return reaped

    async def reclaim_worker_jobs(self, worker_id: str) -> list[uuid.UUID]:
        """
        Fail this worker id's own leftover RUNNING jobs — SAME-HOSTNAME restart hygiene only.

        Called at the worker's STARTUP: a freshly-started process owns NO in-flight task, so any
        RUNNING row still stamped with ITS ``worker_id`` is a leftover from its previous incarnation
        that never marked the row terminal. Marks each such job FAILED and its document FAILED
        (visibly re-ingestable) through the same ``_terminate`` path a manual cancel-force uses.
        Independent of the reap flag — this is startup hygiene, not the periodic reaper.

        SCOPE — what this can and cannot do. ``worker_id`` is the container hostname
        (``socket.gethostname()``), which is stable ONLY across a same-container process restart: a
        dev hot-reload (watchfiles respawns the Python process in place) or an in-container respawn
        keeps the hostname, so this reclaims that incarnation's own orphans INSTANTLY instead of
        waiting out the reaper's stale window. It matches ONLY the caller's own id on purpose — a
        shared/stable key would make a starting replica reclaim a live SIBLING's RUNNING jobs, so the
        own-id key is the only safe one in a scaled fleet.

        It therefore does NOT cover a crash/hard-kill that brings up a NEW container: Docker assigns a
        fresh hostname on recreate, so the orphaned rows carry the OLD id and this matches nothing —
        returning empty is CORRECT there, not a miss. That cross-recreate case is the heartbeat
        REAPER's job (``reap_stale``): once the dead worker's heartbeat ages past the stale cutoff,
        its RUNNING jobs lose the heartbeat veto and are failed. The two paths are complementary —
        reclaim for same-host restarts, the reaper for gone-container crashes.

        Args:
            worker_id (str): The (per-container-lifetime) hostname of the worker reclaiming its OWN
                orphans — never a sibling's.

        Returns:
            list[uuid.UUID]: The reclaimed job ids (empty when this id had no leftovers — the normal
            case after a container RECREATE, where the reaper handles recovery instead).
        """
        error = (
            "reclaimed at worker startup: the previous worker process did not mark this job "
            "terminal (same-container restart, e.g. a dev hot-reload) — presumed orphaned, "
            "re-ingest to retry"
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

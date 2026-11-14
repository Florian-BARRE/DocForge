# ====== Code Summary ======
# JobReaperOps — the force-termination side of the jobs façade: the single ``terminate`` transition
# (job terminal + document mirror for ingest jobs only), the manual force-cancel, the cleanup of
# jobs whose enqueue failed (``abandon`` / ``abandon_ingest``) and the three reaper passes
# (``reap_stale`` killed-worker recovery, ``reap_over_job_timeout`` live-worker watchdog,
# ``reclaim_worker_jobs`` same-hostname restart hygiene). Internal collaborator of JobsFacade.

# ====== Standard Library Imports ======
import uuid
from datetime import UTC, datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import DocumentApi, JobApi
from shared_libs.services.db.postgresql.tables import DocumentStatus, Job, JobKind, JobStatus


class JobReaperOps(LoggerClass):
    """Force-terminate, abandon and reap jobs — every path shares ``terminate``."""

    def __init__(self, postgres: PostgresClient) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres

    async def abandon(self, job_id: uuid.UUID, reason: str) -> None:
        """
        Fail a just-created side-job WITHOUT touching its document — frees the active-job lock.

        The cleanup for a pre-created ``metadata_sync`` row whose enqueue then failed: the committed
        value edit stays the source of truth, but the orphaned row would otherwise (a) hold the
        ``uq_job_active_per_document`` lock — whose predicate covers PENDING — so the next edit's
        ``create_metadata_sync`` hits the unique violation and the next reingest returns ALREADY_ACTIVE,
        and (b) never be reaped (every reap query is RUNNING-only). ``JobApi.mark_terminal`` flips the
        PENDING (or RUNNING) row to FAILED, so it leaves the lock predicate and the document is free
        again. The document status is deliberately NOT mirrored — consistent with ``terminate``'s kind
        gate (a side-job termination never writes document status).

        Best-effort: it runs as cleanup after the edit already committed, on a path the caller treats as
        non-fatal (the response is 200 with ``job_id=null`` regardless), so a DB hiccup here is logged
        and swallowed rather than surfaced as a 500 — never masking the already-reported enqueue error.

        Args:
            job_id (uuid.UUID): The orphaned side-job row to fail.
            reason (str): The human-readable reason recorded on the row.
        """
        # 1. Flip the live row terminal in its own transaction (best-effort — never re-raise).
        try:
            async with self._postgres.session() as session:
                await JobApi.mark_terminal(
                    session,
                    job_id,
                    status=JobStatus.FAILED,
                    reason=reason,
                    finished_at=datetime.now(UTC),
                )
        except Exception:
            self.logger.error(
                f"Failed to abandon orphaned side-job {job_id} after its enqueue failed — the "
                f"document may stay locked until the row is reaped or the job completes",
                exc_info=True,
            )

    async def abandon_ingest(self, job_id: uuid.UUID, reason: str) -> None:
        """
        Fail a just-admitted INGEST job whose enqueue then failed — frees the lock AND fails the doc.

        The ingest counterpart of ``abandon``: an ingestion job is committed PENDING, then handed to
        the queue; if that put fails (a Redis blip) the row would otherwise (a) hold the
        ``uq_job_active_per_document`` lock — whose predicate covers PENDING — so the next reingest
        returns ALREADY_ACTIVE forever, and (b) never be reaped (every reap query is RUNNING-only).
        It routes through ``terminate`` (not ``JobApi.mark_failed``, which is RUNNING-only and would
        silently no-op on the PENDING row): ``mark_terminal`` admits PENDING, so the job flips to FAILED
        and leaves the lock predicate, and because this IS ``kind == INGEST`` the document is mirrored to
        FAILED in the SAME transaction — the never-started document ends visibly re-ingestable, exactly
        like a failed run elsewhere. (Unlike ``abandon``, which deliberately does NOT touch the document:
        a side-job does not own the document lifecycle, an ingest does.)

        Best-effort: it runs as cleanup on the enqueuer's failure path, which the caller already treats
        as non-fatal (it returns False and the route surfaces the enqueue error itself), so a DB hiccup
        here is logged and swallowed rather than raised — never masking the already-reported enqueue
        error with a secondary 500.

        Args:
            job_id (uuid.UUID): The orphaned ingest job row to fail.
            reason (str): The human-readable reason recorded on the row (and mirrored stage).
        """
        # 1. Flip the live PENDING job FAILED and mirror the document FAILED, in one transaction
        #    (best-effort — a cleanup failure must never re-raise over the enqueue error).
        try:
            async with self._postgres.session() as session:
                await self.terminate(
                    session,
                    job_id,
                    job_status=JobStatus.FAILED,
                    doc_status=DocumentStatus.FAILED,
                    reason=reason,
                )
        except Exception:
            self.logger.error(
                f"Failed to abandon orphaned ingest job {job_id} after its enqueue failed — the "
                f"document may stay locked until the row is reaped or re-ingested",
                exc_info=True,
            )

    async def terminate(
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
        Transition ONE job to a terminal status, mirroring onto its document ONLY for ingest jobs.

        The single force-terminate code path shared by cancel-force and the cron reaper: it marks the
        job terminal (closing its open stage row) via ``JobApi.mark_terminal`` and, for an INGEST job,
        flags its owning document terminal, in the SAME transaction. Session-scoped so the reaper can
        loop it over many stale jobs in one unit of work.

        ``mark_terminal`` is a CONDITIONAL transition (it flips only a still-live job and RETURNs it, or
        None when the job already went terminal). A None therefore means a concurrent writer — the
        worker finishing the same job the live-worker watchdog was reaping — already closed it: this
        returns without touching the document, so a fully-ingested document is never flipped to FAILED
        under that race. The document mirror runs ONLY on a winning transition (``job is not None``).

        KIND GATE: the document mirror runs ONLY for ``kind == INGEST``. A side-job (e.g. a
        ``metadata_sync`` re-embed) is minted AFTER the last ingest, so it IS ``get_latest_for_document``
        and the latest-owner guard alone would pass — cancelling/reaping it would then clobber a healthy
        DONE document to CANCELLED/FAILED. Only an ingest run owns the document lifecycle, so only an
        ingest termination mirrors status. The job ROW itself is still terminated for every kind (it
        genuinely is over, and terminating it frees the ``uq_job_active_per_document`` lock).

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
        if job is not None and job.document_id is not None and job.kind == JobKind.INGEST:
            # Ownership edge-guard: only mirror the terminal status onto the DOCUMENT when THIS job is
            # still the document's most-recent run. A newer job (a reingest queued while this one
            # wedged, since reingest always mints a fresh job row) OWNS the document state now — an old
            # reaped/cancelled job must never clobber the newer run's terminal/processing state. The
            # job row itself is always terminated (it genuinely is over); only the shared document
            # write is gated — AND gated on ``kind == INGEST`` (see the KIND GATE note above): a
            # side-job terminating never writes document status. Mirrors ``DocumentApi.finalize_done``'s
            # guard against a racing terminal.
            latest = await JobApi.get_latest_for_document(session, job.document_id)
            if latest is None or latest.id == job_id:
                await DocumentApi.set_status(session, job.document_id, doc_status)
        return job

    async def force_terminate(self, job_id: uuid.UUID, reason: str) -> Job | None:
        """
        Immediately CANCEL a job and its document, regardless of worker state — the manual reaper.

        For a wedged/infinite job (or a queued job cancelled before it runs): marks the job CANCELLED
        and its document CANCELLED now, sharing the reaper's transition semantics via ``terminate``.
        A still-alive worker also stops cooperatively at its next boundary (mark_terminal raises the
        cancel flag) and can never resurrect the job (mark_done/mark_failed no-op once CANCELLED).

        Args:
            job_id (uuid.UUID): The job to force-terminate.
            reason (str): The recorded human-readable reason.

        Returns:
            Job | None: The terminated job, or None when the id is unknown.
        """
        async with self._postgres.session() as session:
            job = await self.terminate(
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
        FAILED (so the document is visibly re-ingestable) — through the SAME ``terminate`` path a
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
                await self.terminate(
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
        rebuild_job_timeout_seconds: float | None = None,
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
        (re-ingestable) through the SAME ``terminate`` path.

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
            rebuild_job_timeout_seconds (float | None): The budget of a collection-wide
                ``rebuild_index`` job (None = treated like any job).

        Returns:
            list[uuid.UUID]: The reaped job ids (empty when nothing is over its job timeout).
        """
        reaped: list[uuid.UUID] = []
        async with self._postgres.session() as session:
            for job, job_timeout in await JobApi.list_over_job_timeout(
                session,
                default_job_timeout_seconds,
                grace_seconds,
                heartbeat_stale_seconds,
                rebuild_job_timeout_seconds,
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
                await self.terminate(
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
        (visibly re-ingestable) through the same ``terminate`` path a manual cancel-force uses.
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
                await self.terminate(
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

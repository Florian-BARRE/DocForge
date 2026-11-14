# ====== Code Summary ======
# JobReaperApi — The reaper's candidate reads: RUNNING jobs silent on a dead / absent worker
# (list_stale) and RUNNING jobs on a LIVE worker past their own job timeout
# (list_over_job_timeout).

# ====== Standard Library Imports ======
from datetime import timedelta

# ====== Third-Party Library Imports ======
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ...tables import (
    Collection,
    Job,
    JobKind,
    JobStatus,
    WorkerHeartbeat,
)


class JobReaperApi:
    """Static data-access API: the reaper's stale / over-timeout candidate reads."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("JobReaperApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def list_stale(
        session: AsyncSession,
        older_than_seconds: float,
        heartbeat_stale_seconds: float,
    ) -> list[Job]:
        """
        Return RUNNING jobs that are BOTH silent past the threshold AND on a dead/absent worker.

        ``updated_at`` only bumps on job-ROW writes (a root-stage START/END, a ForEach counter), so a
        single long SILENT stage — a docling parse of a large scanned PDF, a slow conversion — writes
        nothing between its START and END. A frozen ``updated_at`` therefore no longer proves a job is
        wedged: a HEALTHY job whose one stage runs for >20 min looks identical to an orphaned one. The
        ``worker_heartbeats`` table exists precisely to tell the two apart, so this joins the job to
        its worker's heartbeat and lets a FRESH heartbeat VETO the reap — a job on a live worker is
        never reaped for silence alone. Only a job whose worker's heartbeat is stale (crashed worker)
        or absent (never registered / a RUNNING row with no ``worker_id``, which is only ever an
        orphan since ``mark_running`` always stamps the id) is a genuine reap candidate.

        Both cutoffs use the DATABASE clock (``func.now()``) rather than Python's, so a worker/DB
        clock skew can never mis-classify a live job. PENDING (queued, not yet started) rows are
        excluded. This heartbeat veto is why the fixed global ``older_than_seconds`` need not be scaled
        to each collection's ``job_timeout_seconds``: a live worker vetoes the reap regardless of how
        long its stage runs, and a genuinely-wedged-but-heartbeating worker is caught by arq's outer
        ``job_timeout`` (max job timeout + grace), not by this silence sweep.

        Args:
            session (AsyncSession): The active DB session.
            older_than_seconds (float): A RUNNING job silent (no row write) longer than this is a
                candidate — but only if its worker is also gone.
            heartbeat_stale_seconds (float): A worker whose heartbeat is older than this (or absent)
                is presumed dead, so it cannot veto the reap of its jobs.

        Returns:
            list[Job]: The stale RUNNING jobs on a dead/absent worker, oldest ``updated_at`` first.
        """
        result = await session.execute(
            select(Job)
            .outerjoin(WorkerHeartbeat, WorkerHeartbeat.worker_id == Job.worker_id)
            .where(
                Job.status == JobStatus.RUNNING,
                Job.updated_at < func.now() - timedelta(seconds=older_than_seconds),
                # Reap only when NO live worker vouches for the job: its heartbeat row is absent, or
                # its heartbeat froze past the dead-worker cutoff. A fresh heartbeat here is the veto.
                or_(
                    WorkerHeartbeat.worker_id.is_(None),
                    WorkerHeartbeat.last_seen
                    < func.now() - timedelta(seconds=heartbeat_stale_seconds),
                ),
            )
            .order_by(Job.updated_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_over_job_timeout(
        session: AsyncSession,
        default_job_timeout_seconds: float,
        grace_seconds: float,
        heartbeat_stale_seconds: float,
        rebuild_job_timeout_seconds: float | None = None,
    ) -> list[tuple[Job, float]]:
        """
        Return RUNNING jobs on a LIVE worker whose total age blew past their own job timeout — the watchdog.

        The JOB-LEVEL liveness backstop that closes the heartbeat veto's blind spot: a worker can be
        ALIVE (its arq event loop heartbeats every ~10s) while ONE of its jobs is dead-wedged — an OOM
        killed the parse thread, or a native call hung, and arq's async cancel cannot kill a wedged
        native thread. Its heartbeat is fresh, so ``list_stale`` VETOes the reap and the slot stays
        wedged forever. Liveness measured only at the WORKER level never catches this; this measures it
        at the JOB level instead.

        A job qualifies when its total wall-clock age (``now() - started_at``) exceeds its EFFECTIVE
        job timeout — the per-collection ``job_timeout_seconds`` when set, else the worker's global
        ``default_job_timeout_seconds`` — PLUS ``grace_seconds``. The grace keeps the watchdog conservative:
        the engine's own per-run job timeout fires AT the effective job timeout, so a job the engine is
        about to cancel cleanly is never falsely reaped — only a job that blew past job timeout + grace
        (the engine's cancel demonstrably failed) is caught. The job timeout is the job's REAL
        per-collection job timeout, so a genuinely long docling parse WITHIN its collection's job timeout
        is never touched.

        Mutually exclusive with ``list_stale`` by heartbeat freshness on the SAME cutoff: this path
        requires a FRESH heartbeat (an inner join + ``last_seen`` within ``heartbeat_stale_seconds``),
        while ``list_stale`` requires an absent/stale one. A job therefore lands in exactly one path —
        a live-worker wedge here (``job_timeout_exceeded``) or a dead-worker orphan there
        (``worker_killed``) — never both, so there is no double reap and the attribution is unambiguous.

        Args:
            session (AsyncSession): The active DB session.
            default_job_timeout_seconds (float): The worker's global default job timeout for a collection
                that sets no per-collection ``job_timeout_seconds`` (WORKER_JOB_TIMEOUT_SECONDS).
            grace_seconds (float): Extra margin added on top of the effective job timeout before a job is
                reaped, so a run the engine is about to cancel at its job timeout is never falsely caught.
            heartbeat_stale_seconds (float): The SAME cutoff ``list_stale`` uses — a heartbeat within
                it is FRESH (a live worker), which is exactly what this path targets.
            rebuild_job_timeout_seconds (float | None): The budget of a collection-wide
                ``rebuild_index`` job, which copies the WHOLE collection and has no per-document
                timeout — reaping it at an ingest timeout would lift its guards mid-copy. None = no
                special case.

        Returns:
            list[tuple[Job, float]]: Each over-job-timeout job paired with its effective job timeout in
                seconds (the per-collection value or the default, WITHOUT the grace) so the caller can name
                the exceeded job timeout in the failure reason. Oldest ``started_at`` first.
        """
        # The effective job timeout is a per-row expression (the collection's override or the global
        # default); make_interval turns job timeout + grace into the DB-clock cutoff so a worker/DB skew can
        # never mis-classify, exactly like list_stale's cutoffs.
        effective_job_timeout = func.coalesce(
            Collection.job_timeout_seconds, default_job_timeout_seconds
        )
        if rebuild_job_timeout_seconds is not None:
            effective_job_timeout = case(
                (Job.kind == JobKind.REBUILD_INDEX, rebuild_job_timeout_seconds),
                else_=effective_job_timeout,
            )
        result = await session.execute(
            select(Job, effective_job_timeout)
            .join(Collection, Collection.id == Job.collection_id)
            .join(WorkerHeartbeat, WorkerHeartbeat.worker_id == Job.worker_id)
            .where(
                Job.status == JobStatus.RUNNING,
                Job.started_at.is_not(None),
                Job.started_at
                < func.now()
                - func.make_interval(0, 0, 0, 0, 0, 0, effective_job_timeout + grace_seconds),
                # FRESH heartbeat only: a live worker. The inner join already requires a heartbeat row;
                # this keeps only a heartbeat within the stale cutoff — a stale one is the worker_killed
                # path (list_stale), so the two paths never overlap.
                WorkerHeartbeat.last_seen
                >= func.now() - func.make_interval(0, 0, 0, 0, 0, 0, heartbeat_stale_seconds),
            )
            .order_by(Job.started_at.asc())
        )
        return [(job, float(job_timeout)) for job, job_timeout in result.all()]


__all__ = ["JobReaperApi"]

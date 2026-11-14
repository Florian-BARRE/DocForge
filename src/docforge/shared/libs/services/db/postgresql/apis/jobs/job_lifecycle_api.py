# ====== Code Summary ======
# JobLifecycleApi — Job lifecycle transitions: insert a job, claim it (mark_running), report
# progress / fan-out counters, complete it (mark_done), fail it (mark_failed), flag / probe the
# cooperative cancel, and force a live job terminal (mark_terminal). Every terminal transition is
# a DB-level conditional UPDATE so it serializes on the row lock against a concurrent reaper.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime

# ====== Third-Party Library Imports ======
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.public_models import TextSanitizer

from ...tables import (
    Job,
    JobStageEvent,
    JobStatus,
)


class JobLifecycleApi:
    """Static data-access API: job lifecycle transitions of the ingestion job record."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("JobLifecycleApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def create(session: AsyncSession, job: Job) -> Job:
        """Insert a job and return it (flushed)."""
        session.add(job)
        await session.flush()
        return job

    @staticmethod
    async def mark_running(
        session: AsyncSession,
        job_id: uuid.UUID,
        worker_id: str,
        attempt: int,
        started_at: datetime,
    ) -> None:
        """
        Claim the job for a worker — retry-safe: clears the previous attempt's outcome.

        Guarded against resurrecting a terminal job: a zombie arq re-delivery of a job the reaper (or a
        force-terminate) already marked FAILED/DONE/CANCELLED must NOT flip it back to RUNNING. The
        worker's dequeue-skip guard already bails before this on any terminal status, so this is
        defense-in-depth — no code path can un-finish a finished job. A fresh attempt also starts
        UNFLAGGED: the reaper/force-terminate raise ``cancel_requested`` as a backstop stop signal, so
        clearing it here stops that stale flag from spuriously cancelling a legitimately re-run job at
        its first stage boundary.

        A fresh attempt also wipes the PREVIOUS attempt's OBSERVABILITY residue — the structured
        failure breadcrumb (failed node id/kind/item + error type) and the fan-out item counter — so a
        re-run that succeeds never carries a stale failed-node trace or an old items-done/total from a
        prior failed attempt. This completes the reset above (which cleared only the free-text error +
        finish state); the breadcrumb/counter columns were the missing pieces.
        """
        job = await session.get(Job, job_id)
        # A terminal job is over for good — never re-open it (defense-in-depth behind the dequeue guard).
        if job is None or job.status in JobStatus.terminal():
            return
        job.status = JobStatus.RUNNING
        job.worker_id = worker_id
        job.attempt = attempt
        job.started_at = started_at
        # Reset the previous attempt's state so the UI never shows a stale error on a running job.
        job.error = None
        job.finished_at = None
        job.current_stage = None
        job.progress = 0
        # Clear the backstop cancel flag: a fresh attempt is not a cancellation target.
        job.cancel_requested = False
        # Clear the previous attempt's structured failure breadcrumb: a job that failed at a node and
        # is re-run must not keep pointing at that node once it succeeds.
        job.failed_node_id = None
        job.failed_node_kind = None
        job.failed_item_index = None
        job.error_type = None
        # Clear the fan-out counter too: a stale items-done/total from a prior attempt would otherwise
        # linger on the row until the run happened to enter a foreach stage.
        job.items_done = None
        job.items_total = None

    @staticmethod
    async def set_progress(
        session: AsyncSession, job_id: uuid.UUID, current_stage: str, progress: int
    ) -> None:
        """Report the stage the worker is in and its coarse 0-100 progress."""
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.current_stage = current_stage
        job.progress = progress

    @staticmethod
    async def set_items(
        session: AsyncSession,
        job_id: uuid.UUID,
        items_done: int | None,
        items_total: int | None,
    ) -> None:
        """
        Set the per-item counter for the CURRENT fan-out (foreach) root stage.

        Both values are written verbatim, so passing ``None``/``None`` is the explicit reset the
        worker uses when the job leaves a fan-out stage — a plain "None means skip" patch could
        never clear a stale counter.

        Args:
            session (AsyncSession): The active DB session.
            job_id (uuid.UUID): The job whose counter advances.
            items_done (int | None): Items finished so far (None outside a fan-out).
            items_total (int | None): Fan-out width (None outside a fan-out / until known).
        """
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.items_done = items_done
        job.items_total = items_total

    @staticmethod
    async def mark_done(session: AsyncSession, job_id: uuid.UUID, finished_at: datetime) -> None:
        """
        Complete the job successfully — only while it is still RUNNING (a race-safe transition).

        Expressed as a DB-level CONDITIONAL UPDATE (``WHERE id = :id AND status = 'running'``) rather
        than a load-then-mutate: the live-worker watchdog (``reap_over_job_timeout``) can terminate the SAME
        job in the same millisecond, so the two writers must serialize on the row lock — whoever commits
        first wins, and the loser's ``WHERE`` matches nothing (a clean no-op). This also removes the
        identity-map staleness a Python status guard could never fix: the reaper's own session may still
        hold a cached RUNNING copy of the row from its candidate SELECT, so only a DB-level ``WHERE``
        re-evaluates the truly-committed status. A job already terminal (reaped FAILED, force-terminated
        CANCELLED, or already DONE) is uniformly NOT re-completed — a late ``mark_done`` from the
        still-running task can never resurrect it to DONE (strictly safer than the old CANCELLED-only
        guard, which let a reaped FAILED row flip back to DONE).
        """
        await session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == JobStatus.RUNNING)
            .values(status=JobStatus.DONE, progress=100, finished_at=finished_at)
        )

    @staticmethod
    async def mark_failed(
        session: AsyncSession,
        job_id: uuid.UUID,
        error: str,
        finished_at: datetime,
        failed_node_id: str | None = None,
        failed_node_kind: str | None = None,
        failed_item_index: int | None = None,
        error_type: str | None = None,
    ) -> None:
        """
        Fail the job with its free-text error AND the structured failure breadcrumb.

        A DB-level CONDITIONAL UPDATE (``WHERE id = :id AND status = 'running'``) so it serializes on
        the row lock against a concurrent live-worker reap of the same job (whoever commits first wins;
        the loser is a clean no-op) and never relies on a possibly-stale identity-map copy of the row —
        the same race-free reason as ``mark_done``. A job already terminal (reaped FAILED, force-
        terminated CANCELLED) is not overwritten. This is the normal node-failure path too: the job is
        RUNNING then, so the ``WHERE`` matches and it fails exactly as before.

        Only when the job ACTUALLY transitioned here (rowcount 1) does it also close the job's
        currently-OPEN stage-event row (``finished_at IS NULL``) as failed, so a run cut mid-stage — a
        wall-clock timeout, a hard cancel or the reaper — leaves a red row on the exact stage it died in
        rather than an all-green trace with a silent gap. (A normal node failure has already finalized
        its own stage row via the END event, so that find-open update simply matches nothing.) If a
        concurrent writer already made the job terminal (rowcount 0) the stage timeline is left
        untouched — it belongs to whoever won the transition.

        Args:
            session (AsyncSession): The active DB session.
            job_id (uuid.UUID): The job to fail.
            error (str): The free-text error message (the human-readable reason).
            finished_at (datetime): When the job ended.
            failed_node_id (str | None): The deepest node that raised.
            failed_node_kind (str | None): That node's kind.
            failed_item_index (int | None): The fan-out item index the failure sits in (None outside).
            error_type (str | None): The exception class name (e.g. "TimeoutError").
        """
        # NUL guard on the double-fault path: a parser/provider exception message can echo raw document
        # bytes (incl. a U+0000), which Postgres rejects for a text column — marking a job FAILED must
        # never itself raise a secondary UntranslatableCharacterError.
        error = TextSanitizer.strip_nul(error)
        error_type = TextSanitizer.strip_nul(error_type)
        result = await session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == JobStatus.RUNNING)
            .values(
                status=JobStatus.FAILED,
                error=error,
                finished_at=finished_at,
                failed_node_id=failed_node_id,
                failed_node_kind=failed_node_kind,
                failed_item_index=failed_item_index,
                error_type=error_type,
            )
        )
        # A concurrent writer (the live-worker reaper) already made the job terminal — the transition
        # was a no-op, so its stage timeline is not ours to rewrite.
        if result.rowcount != 1:
            return
        await session.execute(
            update(JobStageEvent)
            .where(JobStageEvent.job_id == job_id, JobStageEvent.finished_at.is_(None))
            .values(status="failed", finished_at=finished_at, detail=error)
        )

    @staticmethod
    async def request_cancel(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
        """
        Raise the cooperative-cancel flag on a job (the worker honours it at its next stage boundary).

        Leaves ``status`` untouched (a RUNNING job stays RUNNING until the worker actually stops), so
        every status-keyed query is unaffected; the flag alone is the signal the worker's stage-boundary
        guard re-reads. Returns the job so the caller can report its post-request state.

        Args:
            session (AsyncSession): The active DB session.
            job_id (uuid.UUID): The job to flag for cancellation.

        Returns:
            Job | None: The flagged job, or None when the id is unknown.
        """
        job = await session.get(Job, job_id)
        if job is None:
            return None
        job.cancel_requested = True
        return job

    @staticmethod
    async def is_cancel_requested(session: AsyncSession, job_id: uuid.UUID) -> bool:
        """Cheap read of a job's stop signal — the worker's between-stages cancellation probe.

        True on either of two stop conditions: the ``cancel_requested`` flag is set, OR the job row no
        longer exists. A VANISHED row means the collection (and so the job, via cascade) was deleted
        mid-run — the worker must stop BEFORE its persist phase writes document/chunk rows the cascade
        is about to remove (an FK IntegrityError). A missing row is therefore a stop, never a "keep
        going": the worker only ever probes a job it is actively running, so the id cannot be spurious.
        """
        result = await session.execute(select(Job.id, Job.cancel_requested).where(Job.id == job_id))
        row = result.first()
        # The job row is gone (collection deleted mid-run, cascade) — stop the run cleanly.
        if row is None:
            return True
        return bool(row.cancel_requested)

    @staticmethod
    async def mark_terminal(
        session: AsyncSession,
        job_id: uuid.UUID,
        status: JobStatus,
        reason: str,
        finished_at: datetime,
        error_type: str | None = None,
    ) -> Job | None:
        """
        Force a non-terminal job to a terminal ``status`` with a reason — the shared stop primitive.

        Both the force-terminate (CANCELLED) and the cron reaper (FAILED) transition a job the same
        way: set the terminal status + reason + finish time, raise ``cancel_requested`` as a backstop
        stop signal for a still-alive worker, and CLOSE the job's currently-open stage-event row (the
        stage it was cut in) as terminal, so the trace shows a red/stopped stage rather than a silent
        gap.

        Expressed as a DB-level CONDITIONAL UPDATE guarded on the job still being LIVE
        (``status IN ('pending', 'running')``) with ``RETURNING``, NOT a load-then-mutate: the live-
        worker watchdog (``reap_over_job_timeout``) targets a job while its worker races to finish it, so the
        two writers MUST serialize on the row lock. The guard is the ONLY concurrency-safe transition —
        an in-Python ``if terminal: return`` check would read a STALE row: the reaper's own session
        cached the RUNNING job in its identity map when ``list_over_job_timeout`` selected it, so a later
        ``session.get`` never re-reads the worker's committed DONE. Only ``RETURNING`` on a committed-
        data ``WHERE`` re-evaluates the real status. The guard admits ``pending`` too so a QUEUED job
        can still be force-cancelled before it ever ran; it excludes the terminal states, so terminating
        an already-terminal job is a no-op (you cannot cancel a finished job — the "worker finished
        first" race returns None, and the caller then skips the document mirror).

        Args:
            session (AsyncSession): The active DB session.
            job_id (uuid.UUID): The job to terminate.
            status (JobStatus): The terminal status (CANCELLED or FAILED).
            reason (str): The human-readable reason recorded on the job and its open stage row.
            finished_at (datetime): When the job was terminated.
            error_type (str | None): The structured cause stamped on ``error_type`` when the
                terminate is an ATTRIBUTED failure (the reaper's ``worker_killed`` /
                ``job_timeout_exceeded``); None leaves the column untouched (a plain cancel carries no
                exception-class attribution).

        Returns:
            Job | None: The freshly-terminated job (so the caller can read its ``document_id``) when
                THIS call won the transition, or None when the job was already terminal / unknown (the
                caller must then NOT mirror the document).
        """
        # 0. NUL guard on the terminate path (shares the double-fault concern with ``mark_failed``): the
        #    reason/error_type can carry a U+0000 echoed from raw document bytes, which Postgres rejects
        #    for a text column — terminating a job must never itself raise.
        reason = TextSanitizer.strip_nul(reason)
        error_type = TextSanitizer.strip_nul(error_type)
        # 1. Build the values written on a winning transition. error_type is set only when the caller
        #    supplied one (the reaper's watchdog paths); a None leaves any prior value untouched so a
        #    plain cancel does not fabricate an error_type.
        values: dict[str, object] = {
            "status": status,
            "error": reason,
            "finished_at": finished_at,
            "cancel_requested": True,
        }
        if error_type is not None:
            values["error_type"] = error_type
        # 2. Conditional transition on committed data: only a still-live (pending/running) row flips,
        #    and RETURNING hands back the fresh ORM row (populate_existing refreshes the identity-map
        #    copy the reaper's candidate SELECT may hold).
        result = await session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING]))
            .values(**values)
            .returning(Job)
            .execution_options(populate_existing=True)
        )
        job = result.scalars().first()
        # 3. No row transitioned — the job was already terminal (a concurrent reap, or a worker that
        #    finished first) or the id is unknown. Return None so the caller skips the document mirror.
        if job is None:
            return None
        # 4. Won the transition: close the stage row it was cut in as terminal (a silent-gap guard).
        await session.execute(
            update(JobStageEvent)
            .where(JobStageEvent.job_id == job_id, JobStageEvent.finished_at.is_(None))
            .values(status=status.value, finished_at=finished_at, detail=reason)
        )
        return job


__all__ = ["JobLifecycleApi"]

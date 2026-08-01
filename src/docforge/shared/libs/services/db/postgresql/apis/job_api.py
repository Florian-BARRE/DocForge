# ====== Code Summary ======
# JobApi — the data-access API for ingestion observability: the job record and its per-stage event
# timeline. The job LIFECYCLE is expressed as explicit transitions (mark_running / set_progress /
# mark_done / mark_failed) rather than a generic patch — mark_running is retry-safe and clears the
# previous attempt's error/finish state, which a None-means-skip patch could never reset. And
# `record_event` appends to the stage timeline the live-status UI reads.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime, timedelta

# ====== Third-Party Library Imports ======
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ..tables import Job, JobStageEvent, JobStatus


class JobApi:
    """Static data-access API for ingestion jobs and their stage timeline."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("JobApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def create(session: AsyncSession, job: Job) -> Job:
        """Insert a job and return it (flushed)."""
        session.add(job)
        await session.flush()
        return job

    @staticmethod
    async def get(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
        """Fetch a job by id, or None."""
        return await session.get(Job, job_id)

    @staticmethod
    async def mark_running(
        session: AsyncSession,
        job_id: uuid.UUID,
        worker_id: str,
        attempt: int,
        started_at: datetime,
    ) -> None:
        """Claim the job for a worker — retry-safe: clears the previous attempt's outcome."""
        job = await session.get(Job, job_id)
        if job is None:
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
    async def mark_done(session: AsyncSession, job_id: uuid.UUID, finished_at: datetime) -> None:
        """Complete the job successfully."""
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.DONE
        job.progress = 100
        job.finished_at = finished_at

    @staticmethod
    async def mark_failed(
        session: AsyncSession, job_id: uuid.UUID, error: str, finished_at: datetime
    ) -> None:
        """Fail the job with its error message."""
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.FAILED
        job.error = error
        job.finished_at = finished_at

    @staticmethod
    async def record_event(session: AsyncSession, event: JobStageEvent) -> JobStageEvent:
        """Append a stage event to the job's timeline and return it."""
        session.add(event)
        await session.flush()
        return event

    @staticmethod
    async def list_events(session: AsyncSession, job_id: uuid.UUID) -> list[JobStageEvent]:
        """Return a job's per-node trace, in execution order."""
        result = await session.execute(
            select(JobStageEvent)
            .where(JobStageEvent.job_id == job_id)
            .order_by(JobStageEvent.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_active(session: AsyncSession) -> list[Job]:
        """Return every RUNNING job — the live view of what the workers are doing."""
        result = await session.execute(
            select(Job).where(Job.status == JobStatus.RUNNING).order_by(Job.started_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_stale(session: AsyncSession, older_than_seconds: float) -> list[Job]:
        """
        Return RUNNING jobs whose ``updated_at`` froze past the threshold — the reap candidates.

        The cutoff uses the DATABASE clock (``func.now()``) rather than Python's, so a clock skew
        between a worker and Postgres can never mis-classify a live job as stale. ``updated_at``
        bumps on every progress/stage write (TimestampedMixin ``onupdate``), so a frozen value is
        exactly the orphaned/wedged signal. PENDING (queued, not yet started) rows are excluded.

        Args:
            session (AsyncSession): The active DB session.
            older_than_seconds (float): A RUNNING job idle longer than this is stale.

        Returns:
            list[Job]: The stale RUNNING jobs, oldest ``updated_at`` first.
        """
        result = await session.execute(
            select(Job)
            .where(
                Job.status == JobStatus.RUNNING,
                Job.updated_at < func.now() - timedelta(seconds=older_than_seconds),
            )
            .order_by(Job.updated_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_for_collection(session: AsyncSession, collection_id: uuid.UUID) -> list[Job]:
        """Return a collection's jobs, newest first."""
        result = await session.execute(
            select(Job).where(Job.collection_id == collection_id).order_by(Job.created_at.desc())
        )
        return list(result.scalars().all())


__all__ = ["JobApi"]

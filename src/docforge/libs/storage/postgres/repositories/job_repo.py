# ====== Code Summary ======
# JobRepository — CRUD operations for the job table.
# Each job tracks one arq pipeline execution: from admission to done/failed.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from datetime import datetime

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from libs.storage.postgres.models import JobModel


class JobRepository(LoggerClass):
    """
    CRUD operations for the job table.

    Each document ingest creates one JobModel, which the arq worker updates as it progresses.
    The /jobs/{id} API surfaces this to clients polling for pipeline status.
    """

    def __init__(self) -> None:
        """Initialize the JobRepository logger."""
        LoggerClass.__init__(self)

    async def create(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
        collection_id: uuid.UUID,
    ) -> JobModel:
        """
        Create a new pending job record for a document admission.

        Args:
            session (AsyncSession): Active DB session.
            document_id (uuid.UUID): ID of the document being processed.
            collection_id (uuid.UUID): ID of the target collection.

        Returns:
            JobModel: The newly created job record.
        """
        job = JobModel(
            document_id=document_id,
            collection_id=collection_id,
            status="pending",
        )
        session.add(job)
        await session.flush()
        self.logger.debug(f"Created job {job.id} for document {document_id}.")
        return job

    async def list_by_collection(
        self,
        session: AsyncSession,
        collection_id: uuid.UUID,
        *,
        status: str | None = None,
        document_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[JobModel], int]:
        """
        List a collection's jobs (newest first) with optional filters + pagination.

        Args:
            session (AsyncSession): Active session.
            collection_id (uuid.UUID): Parent collection.
            status (str | None): Restrict to this job status.
            document_id (uuid.UUID | None): Restrict to one document's jobs.
            limit (int): Page size.
            offset (int): Page offset.

        Returns:
            tuple: ``(page_of_jobs, total_matching)``.
        """
        # 1. Shared filter clause
        clause = [JobModel.collection_id == collection_id]
        if status is not None:
            clause.append(JobModel.status == status)
        if document_id is not None:
            clause.append(JobModel.document_id == document_id)

        # 2. Total count (before pagination)
        total = await session.scalar(select(func.count()).select_from(JobModel).where(*clause))

        # 3. Page of rows (newest first)
        result = await session.execute(
            select(JobModel).where(*clause)
            .order_by(JobModel.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), int(total or 0)

    async def list_by_document(
        self, session: AsyncSession, document_id: uuid.UUID
    ) -> list[JobModel]:
        """Return all jobs for a document, newest first (for per-document logs)."""
        result = await session.execute(
            select(JobModel).where(JobModel.document_id == document_id)
            .order_by(JobModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
    ) -> JobModel | None:
        """
        Retrieve a job by its primary key.

        Args:
            session (AsyncSession): Active DB session.
            job_id (uuid.UUID): Job primary key.

        Returns:
            JobModel | None: The job record, or None if not found.
        """
        result = await session.execute(
            select(JobModel).where(JobModel.id == job_id)
        )
        return result.scalar_one_or_none()

    async def list_by_status(
        self,
        session: AsyncSession,
        status: str,
    ) -> list[JobModel]:
        """
        Return all jobs with a given status, newest first.

        Used by the worker startup hook to detect jobs left in ``"running"`` state
        by a crashed worker instance (stuck jobs).

        Args:
            session (AsyncSession): Active DB session.
            status (str): Job status to filter on (e.g. ``"running"``).

        Returns:
            list[JobModel]: All matching jobs, newest first.
        """
        result = await session.execute(
            select(JobModel).where(JobModel.status == status)
            .order_by(JobModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        status: str,
        error: str | None = None,
        budget_spent: float | None = None,
    ) -> None:
        """
        Update the status (and optionally error/cost) of an existing job.

        Args:
            session (AsyncSession): Active DB session.
            job_id (uuid.UUID): Job primary key.
            status (str): New status: ``"running"``, ``"done"``, or ``"failed"``.
            error (str | None): Error message to store (only for ``"failed"`` status).
            budget_spent (float | None): Total API cost incurred by this job.
        """
        result = await session.execute(
            select(JobModel).where(JobModel.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            self.logger.warning(f"update_status: job {job_id} not found — skipping.")
            return

        # 1. Apply status transition
        job.status = status
        if error is not None:
            job.error = error
        if budget_spent is not None:
            job.budget_spent = budget_spent

        await session.flush()
        self.logger.debug(f"Job {job_id} status → {status}.")

    async def list_jobs(
        self,
        session: AsyncSession,
        *,
        status: str | None = None,
        collection_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[JobModel], int]:
        """
        List jobs across all collections (newest first) with optional filters + pagination.

        Unlike ``list_by_collection``, this is the global view backing ``GET /api/v1/jobs`` —
        the monitoring surface that is not scoped to a single collection.

        Args:
            session (AsyncSession): Active session.
            status (str | None): Restrict to this job status.
            collection_id (uuid.UUID | None): Restrict to one collection.
            limit (int): Page size.
            offset (int): Page offset.

        Returns:
            tuple: ``(page_of_jobs, total_matching)``.
        """
        # 1. Build the optional filter clause
        clause = []
        if status is not None:
            clause.append(JobModel.status == status)
        if collection_id is not None:
            clause.append(JobModel.collection_id == collection_id)

        # 2. Total count (before pagination)
        total = await session.scalar(select(func.count()).select_from(JobModel).where(*clause))

        # 3. Page of rows (newest first)
        result = await session.execute(
            select(JobModel).where(*clause)
            .order_by(JobModel.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all()), int(total or 0)

    async def count_by_status(
        self,
        session: AsyncSession,
        *,
        collection_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        """
        Return a ``{status: count}`` map over jobs, optionally scoped to a collection.

        Backs the monitoring overview/queue endpoints — a single grouped query instead of
        one COUNT per status. Statuses with zero rows are simply absent from the map.

        Args:
            session (AsyncSession): Active session.
            collection_id (uuid.UUID | None): Restrict the tally to one collection.

        Returns:
            dict[str, int]: Count of jobs per status value.
        """
        # 1. Grouped count over the status column
        clause = [] if collection_id is None else [JobModel.collection_id == collection_id]
        result = await session.execute(
            select(JobModel.status, func.count())
            .where(*clause).group_by(JobModel.status)
        )
        return {status: int(count) for status, count in result.all()}

    async def count_finished_since(
        self,
        session: AsyncSession,
        since: datetime,
        *,
        collection_id: uuid.UUID | None = None,
    ) -> int:
        """
        Count jobs that reached a terminal state (``done``/``failed``) at or after ``since``.

        Drives the throughput metric (jobs/min) on the monitoring queue endpoint. Uses
        ``finished_at`` so retried jobs are counted once, at their final transition. The optional
        ``collection_id`` keeps it symmetric with ``count_by_status`` for a future per-collection
        overview (brique B/C).

        Args:
            session (AsyncSession): Active session.
            since (datetime): Lower bound (timezone-aware) for ``finished_at``.
            collection_id (uuid.UUID | None): Restrict the tally to one collection.

        Returns:
            int: Number of jobs finished in the window.
        """
        # 1. Count terminal jobs within the time window (optionally scoped to a collection)
        clause = [JobModel.finished_at.is_not(None), JobModel.finished_at >= since]
        if collection_id is not None:
            clause.append(JobModel.collection_id == collection_id)
        total = await session.scalar(
            select(func.count()).select_from(JobModel).where(*clause)
        )
        return int(total or 0)

    async def mark_running(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        *,
        worker_id: str,
        attempt: int,
        started_at: datetime,
    ) -> None:
        """
        Transition a job to ``running`` and record worker attribution + start time.

        Args:
            session (AsyncSession): Active session.
            job_id (uuid.UUID): Job primary key.
            worker_id (str): Identifier of the claiming worker process.
            attempt (int): 1-based arq retry attempt number.
            started_at (datetime): Timezone-aware execution start timestamp.
        """
        # 1. Load the job (skip silently if it vanished)
        job = await self.get_by_id(session, job_id)
        if job is None:
            self.logger.warning(f"mark_running: job {job_id} not found — skipping.")
            return

        # 2. Stamp running state + worker attribution
        job.status = "running"
        job.worker_id = worker_id
        job.attempt = attempt
        job.started_at = started_at
        job.current_stage = None
        job.progress = 0
        await session.flush()
        self.logger.debug(f"Job {job_id} → running on worker {worker_id} (attempt {attempt}).")

    async def mark_finished(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        status: str,
        *,
        finished_at: datetime,
        error: str | None = None,
        budget_spent: float | None = None,
    ) -> None:
        """
        Transition a job to a terminal state (``done``/``failed``) and record finish time.

        Args:
            session (AsyncSession): Active session.
            job_id (uuid.UUID): Job primary key.
            status (str): Terminal status (``"done"`` or ``"failed"``).
            finished_at (datetime): Timezone-aware completion timestamp.
            error (str | None): Error message (for ``"failed"``).
            budget_spent (float | None): Total API cost incurred by this job.
        """
        # 1. Load the job (skip silently if it vanished)
        job = await self.get_by_id(session, job_id)
        if job is None:
            self.logger.warning(f"mark_finished: job {job_id} not found — skipping.")
            return

        # 2. Stamp terminal state. A done job reads as 100% with no stage in flight; a failed
        #    job keeps current_stage so the UI can show where it died.
        job.status = status
        job.finished_at = finished_at
        if error is not None:
            job.error = error
        if budget_spent is not None:
            job.budget_spent = budget_spent
        if status == "done":
            job.progress = 100
            job.current_stage = None
        await session.flush()
        self.logger.debug(f"Job {job_id} → {status} (finished).")

    async def update_progress(
        self,
        session: AsyncSession,
        job_id: uuid.UUID,
        current_stage: str,
        progress: int,
    ) -> None:
        """
        Update the coarse live-progress signal (current stage + percent) of a running job.

        Args:
            session (AsyncSession): Active session.
            job_id (uuid.UUID): Job primary key.
            current_stage (str): Stage node id currently executing (e.g. ``"s4"``).
            progress (int): Completion percentage in ``[0, 100]``.
        """
        # 1. Load the job (skip silently if it vanished)
        job = await self.get_by_id(session, job_id)
        if job is None:
            self.logger.warning(f"update_progress: job {job_id} not found — skipping.")
            return

        # 2. Clamp + apply the progress signal
        job.current_stage = current_stage
        job.progress = max(0, min(100, progress))
        await session.flush()

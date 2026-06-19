# ====== Code Summary ======
# JobRepository — CRUD operations for the job table.
# Each job tracks one arq pipeline execution: from admission to done/failed.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid

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

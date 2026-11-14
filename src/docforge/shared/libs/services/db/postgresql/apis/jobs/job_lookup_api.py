# ====== Code Summary ======
# JobLookupApi — Plain job lookups: one job by id, a document's latest / latest-DONE / live job, a
# collection's jobs (list + count) and the RUNNING / live job lists.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ...tables import (
    Job,
    JobStatus,
)


class JobLookupApi:
    """Static data-access API: plain job lookups by id, document and collection."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("JobLookupApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def get(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
        """Fetch a job by id, or None."""
        return await session.get(Job, job_id)

    @staticmethod
    async def get_latest_for_document(session: AsyncSession, document_id: uuid.UUID) -> Job | None:
        """The most recent ingestion job for a document (its last run's provenance), or None."""
        result = await session.execute(
            select(Job)
            .where(Job.document_id == document_id)
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(1)
        )
        return result.scalars().first()

    @staticmethod
    async def get_latest_successful_for_document(
        session: AsyncSession, document_id: uuid.UUID
    ) -> Job | None:
        """
        The most recent DONE job for a document — the run that produced its CURRENT persisted IR.

        Provenance must describe the run that actually yielded the IR/chunks on display, so a later
        FAILED (or still-running) job must never shadow the successful run behind it: reading the plain
        latest job would attribute the displayed IR to a run that produced nothing. A document whose
        only runs failed has no provenance to show — returns None (the surface reports it unavailable).

        Args:
            session (AsyncSession): The active DB session.
            document_id (uuid.UUID): The document whose last successful run is queried.

        Returns:
            Job | None: The latest DONE job, or None when the document has never completed a run.
        """
        result = await session.execute(
            select(Job)
            .where(Job.document_id == document_id, Job.status == JobStatus.DONE)
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(1)
        )
        return result.scalars().first()

    @staticmethod
    async def get_active_for_document(session: AsyncSession, document_id: uuid.UUID) -> Job | None:
        """
        Return the document's live (PENDING or RUNNING) ingestion job — newest first — or None.

        The guard the reingest admission consults so a document whose run is already queued or
        executing never mints a SECOND concurrent job: two parallel runs of one document interleave
        their Qdrant upsert + stale-point purge and strand the loser's
        points as live orphans while Postgres keeps only the winner's chunks. Only the non-terminal
        statuses count — DONE/FAILED/CANCELLED are over, so a terminal-only history reads as idle.

        Args:
            session (AsyncSession): The active DB session.
            document_id (uuid.UUID): The document whose in-flight run is probed.

        Returns:
            Job | None: The live job (PENDING/RUNNING), or None when the document is idle.
        """
        result = await session.execute(
            select(Job)
            .where(
                Job.document_id == document_id,
                Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
            )
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(1)
        )
        return result.scalars().first()

    @staticmethod
    async def list_for_collection(session: AsyncSession, collection_id: uuid.UUID) -> list[Job]:
        """Return a collection's jobs, newest first."""
        result = await session.execute(
            select(Job).where(Job.collection_id == collection_id).order_by(Job.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def count_for_collection(session: AsyncSession, collection_id: uuid.UUID) -> int:
        """Count a collection's jobs — the pager's total (independent of limit/offset)."""
        result = await session.execute(
            select(func.count()).select_from(Job).where(Job.collection_id == collection_id)
        )
        return int(result.scalar_one())

    @staticmethod
    async def list_active(session: AsyncSession) -> list[Job]:
        """Return every RUNNING job — the live view of what the workers are doing."""
        result = await session.execute(
            select(Job).where(Job.status == JobStatus.RUNNING).order_by(Job.started_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_active_for_collection(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> list[Job]:
        """Return a collection's live (PENDING or RUNNING) jobs — the in-flight runs a delete must stop.

        A collection delete cancels these FIRST so a live worker aborts its run gracefully at its next
        stage boundary, before the cascade removes the rows its mid-run inserts reference. Terminal
        jobs (DONE/FAILED/CANCELLED) are already over, so they never qualify.

        Args:
            session (AsyncSession): The active DB session.
            collection_id (uuid.UUID): The collection whose in-flight jobs are listed.

        Returns:
            list[Job]: The collection's PENDING/RUNNING jobs (empty when none are in flight).
        """
        result = await session.execute(
            select(Job).where(
                Job.collection_id == collection_id,
                Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
            )
        )
        return list(result.scalars().all())


__all__ = ["JobLookupApi"]

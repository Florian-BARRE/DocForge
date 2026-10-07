# ====== Code Summary ======
# RebuildJobApi — the Postgres queries behind the rebuild_index job: the collection-row locks that
# serialise a rebuild admission against ingest admissions (FOR UPDATE vs FOR SHARE), the live-job
# lookups (the active rebuild, the other live jobs), and the reads the post-swap reconciliation needs
# (the chunk enabled overrides, the collection's surviving document ids).

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Local Project Imports ======
from ..tables import Chunk, Collection, Document, Job, JobKind, JobStatus

# The live job states (the predicate of both active-job partial unique indexes).
_ACTIVE = (JobStatus.PENDING, JobStatus.RUNNING)


class RebuildJobApi:
    """Static Postgres queries for the rebuild_index job (admission locks + reconciliation reads)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("RebuildJobApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def lock_collection(
        session: AsyncSession, collection_id: uuid.UUID, *, exclusive: bool
    ) -> bool:
        """
        Lock the collection row for the transaction — FOR UPDATE (rebuild) or FOR SHARE (ingest).

        The two lock modes conflict, so a rebuild admission and an ingest admission on the same
        collection serialise: whichever commits second sees the first one's job row.

        Returns:
            bool: False when the collection does not exist.
        """
        query = select(Collection.id).where(Collection.id == collection_id)
        query = query.with_for_update() if exclusive else query.with_for_update(read=True)
        return (await session.execute(query)).scalar_one_or_none() is not None

    @staticmethod
    async def active_rebuild(session: AsyncSession, collection_id: uuid.UUID) -> Job | None:
        """Return the collection's live (pending/running) rebuild_index job, or None."""
        result = await session.execute(
            select(Job).where(
                Job.collection_id == collection_id,
                Job.kind == JobKind.REBUILD_INDEX,
                Job.status.in_(_ACTIVE),
            )
        )
        return result.scalars().first()

    @staticmethod
    async def active_job_ids(
        session: AsyncSession, collection_id: uuid.UUID, exclude: uuid.UUID | None = None
    ) -> list[uuid.UUID]:
        """Return the ids of the collection's live jobs of any kind, minus ``exclude``."""
        query = select(Job.id).where(Job.collection_id == collection_id, Job.status.in_(_ACTIVE))
        if exclude is not None:
            query = query.where(Job.id != exclude)
        return list((await session.execute(query)).scalars().all())

    @staticmethod
    async def chunk_overrides(
        session: AsyncSession, collection_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str, bool]]:
        """Return ``(chunk_id, role, enabled_override)`` for every indexed chunk with an override."""
        result = await session.execute(
            select(Chunk.id, Chunk.role, Chunk.enabled_override)
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Document.collection_id == collection_id,
                Chunk.enabled_override.is_not(None),
                Chunk.is_indexed.is_(True),
            )
        )
        return [(row[0], row[1], bool(row[2])) for row in result.all()]

    @staticmethod
    async def document_ids(session: AsyncSession, collection_id: uuid.UUID) -> set[uuid.UUID]:
        """Return the ids of every document the collection still has."""
        result = await session.execute(
            select(Document.id).where(Document.collection_id == collection_id)
        )
        return set(result.scalars().all())


__all__ = ["RebuildJobApi"]

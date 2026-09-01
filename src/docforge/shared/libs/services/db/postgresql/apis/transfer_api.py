# ====== Code Summary ======
# TransferApi — the data-access API for the `collection_transfer` tracking row: create the record,
# fetch it, and patch its lifecycle fields (status/progress/stage/counts/artifact/timestamps). It is
# the status surface the router polls and the durable reference the download endpoint reads, so every
# write goes through one narrow ``update`` that leaves unset fields untouched. Postgres-only,
# session-driven — the façade composes it.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ..tables import CollectionTransfer, TransferKind, TransferStatus


class TransferApi:
    """Static data-access API for the collection-transfer tracking row."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("TransferApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def create(session: AsyncSession, transfer: CollectionTransfer) -> CollectionTransfer:
        """Insert a transfer row and return it (flushed, so its id is populated)."""
        session.add(transfer)
        await session.flush()
        return transfer

    @staticmethod
    async def get(session: AsyncSession, transfer_id: uuid.UUID) -> CollectionTransfer | None:
        """Fetch a transfer row by id, or None."""
        return await session.get(CollectionTransfer, transfer_id)

    @staticmethod
    async def list_expired(session: AsyncSession, now: datetime) -> list[CollectionTransfer]:
        """Return every EXPORT transfer whose bundle has expired and still has an S3 object to reclaim.

        Only export rows carry a produced bundle; ``expires_at`` NULL means keep-forever (skipped),
        and a row with no ``s3_key`` has nothing to delete. The GC caller drops the S3 object + the row.
        """
        result = await session.execute(
            select(CollectionTransfer).where(
                CollectionTransfer.kind == TransferKind.EXPORT,
                CollectionTransfer.s3_key.is_not(None),
                CollectionTransfer.expires_at.is_not(None),
                CollectionTransfer.expires_at < now,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def delete(session: AsyncSession, transfer_id: uuid.UUID) -> None:
        """Delete a transfer tracking row (its bundle bytes are the caller's to reclaim first)."""
        row = await session.get(CollectionTransfer, transfer_id)
        if row is not None:
            await session.delete(row)

    @staticmethod
    async def update(
        session: AsyncSession,
        transfer_id: uuid.UUID,
        *,
        status: TransferStatus | None = None,
        progress: int | None = None,
        stage: str | None = None,
        counts: dict[str, Any] | None = None,
        error: str | None = None,
        collection_id: uuid.UUID | None = None,
        collection_name: str | None = None,
        s3_key: str | None = None,
        size_bytes: int | None = None,
        format_version: int | None = None,
        dense_dim: int | None = None,
        expires_at: datetime | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        """Patch the provided lifecycle fields on a transfer row (None means 'leave unchanged')."""
        row = await session.get(CollectionTransfer, transfer_id)
        if row is None:
            return
        if status is not None:
            row.status = status
        if progress is not None:
            row.progress = progress
        if stage is not None:
            row.stage = stage
        if counts is not None:
            row.counts = counts
        if error is not None:
            row.error = error
        if collection_id is not None:
            row.collection_id = collection_id
        if collection_name is not None:
            row.collection_name = collection_name
        if s3_key is not None:
            row.s3_key = s3_key
        if size_bytes is not None:
            row.size_bytes = size_bytes
        if format_version is not None:
            row.format_version = format_version
        if dense_dim is not None:
            row.dense_dim = dense_dim
        if expires_at is not None:
            row.expires_at = expires_at
        if started_at is not None:
            row.started_at = started_at
        if finished_at is not None:
            row.finished_at = finished_at


__all__ = ["TransferApi"]

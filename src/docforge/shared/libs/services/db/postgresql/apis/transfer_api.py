# ====== Code Summary ======
# TransferApi — the data-access API for the `collection_transfer` tracking row: create the record,
# fetch it, and patch its lifecycle fields (status/progress/stage/counts/artifact/timestamps). It is
# the status surface the router polls and the durable reference the download endpoint reads, so every
# write goes through one narrow ``update`` that leaves unset fields untouched. Postgres-only,
# session-driven — the façade composes it.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime, timedelta
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from ..tables import CollectionTransfer, TransferStatus


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
        """Return every transfer whose S3 object has expired and is still reclaimable — both kinds.

        Two kinds of object leak here: an EXPORT's produced bundle and an IMPORT's STAGED bundle. Both
        carry an ``s3_key`` and get an ``expires_at`` stamp (export: at ``set_artifact``; import: at
        admission); ``expires_at`` NULL means keep-forever (skipped), and a row with no ``s3_key`` has
        nothing to delete. The GC caller drops the S3 object + the row. ``kind`` is NOT filtered — the
        sweep is kind-agnostic so a failed/abandoned import is reclaimed exactly like an expired export.
        """
        result = await session.execute(
            select(CollectionTransfer).where(
                CollectionTransfer.s3_key.is_not(None),
                CollectionTransfer.expires_at.is_not(None),
                CollectionTransfer.expires_at < now,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_stale(
        session: AsyncSession, older_than_seconds: float
    ) -> list[CollectionTransfer]:
        """Return every RUNNING transfer whose ``updated_at`` froze past the staleness horizon.

        A collection_transfer row has NO heartbeat, so ``updated_at`` (bumped on every lifecycle write:
        mark_running, report_progress, mark_done/failed) is the only liveness signal. Between
        mark_running and the terminal write the engine's progress callback only LOGS — it does not
        write the row — so ``updated_at`` effectively freezes at the run's start for the whole run.
        The caller therefore passes a horizon ABOVE arq's hard job_timeout ceiling: no transfer can
        legitimately run that long (arq kills it first), so any RUNNING row older than the horizon is
        genuinely orphaned (a hard kill or an arq timeout that raised BaseException past the task's
        ``except``), never a healthy long run. Oldest first, so a backlog is cleared deterministically.

        Args:
            older_than_seconds (float): The staleness horizon; a RUNNING row untouched longer than
                this is presumed orphaned.

        Returns:
            list[CollectionTransfer]: The stale RUNNING transfer rows (empty when none qualify).
        """
        result = await session.execute(
            select(CollectionTransfer)
            .where(
                CollectionTransfer.status == TransferStatus.RUNNING,
                CollectionTransfer.updated_at < func.now() - timedelta(seconds=older_than_seconds),
            )
            .order_by(CollectionTransfer.updated_at.asc())
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

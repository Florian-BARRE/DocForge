# ====== Code Summary ======
# TransferTrackerFacade — the lifecycle of a `collection_transfer` tracking row: the router creates
# it PENDING and enqueues the worker task with its id; the worker task drives it RUNNING → DONE /
# FAILED, streaming progress and (for export) stamping the bundle artifact reference the download
# endpoint later reads. Distinct from CollectionTransferFacade (which moves the actual data): this
# façade only touches the one tracking row, so the status surface and the heavy engine stay decoupled.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from typing import Any

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass

from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import TransferApi
from shared_libs.services.db.postgresql.tables import (
    CollectionTransfer,
    TransferKind,
    TransferStatus,
)


class TransferTrackerFacade(LoggerClass):
    """Create + drive a collection-transfer tracking row through its lifecycle."""

    def __init__(self, postgres: PostgresClient) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres

    async def create(
        self,
        kind: TransferKind,
        *,
        collection_id: uuid.UUID | None = None,
        collection_name: str | None = None,
        s3_key: str | None = None,
        expires_at: datetime | None = None,
    ) -> CollectionTransfer:
        """
        Insert a PENDING transfer row (the router does this before enqueue) and return it.

        ``expires_at`` is stamped at admission for an IMPORT (its staged bundle's reclaim horizon, so
        a failed/abandoned import is swept by the transfer GC like an expired export); an EXPORT stamps
        it later, at ``set_artifact``, once its bundle exists.
        """
        row = CollectionTransfer(
            kind=kind,
            status=TransferStatus.PENDING,
            collection_id=collection_id,
            collection_name=collection_name,
            s3_key=s3_key,
            expires_at=expires_at,
        )
        async with self._postgres.session() as session:
            return await TransferApi.create(session, row)

    async def get(self, transfer_id: uuid.UUID) -> CollectionTransfer | None:
        """Fetch a transfer row by id."""
        async with self._postgres.session() as session:
            return await TransferApi.get(session, transfer_id)

    async def mark_running(self, transfer_id: uuid.UUID, started_at: datetime) -> None:
        """Flip the row to RUNNING as the worker claims it."""
        async with self._postgres.session() as session:
            await TransferApi.update(
                session, transfer_id, status=TransferStatus.RUNNING, started_at=started_at
            )

    async def report_progress(self, transfer_id: uuid.UUID, stage: str, progress: int) -> None:
        """Record the current stage + coarse percentage (best-effort live progress)."""
        async with self._postgres.session() as session:
            await TransferApi.update(session, transfer_id, stage=stage, progress=progress)

    async def set_artifact(
        self,
        transfer_id: uuid.UUID,
        *,
        s3_key: str,
        size_bytes: int,
        format_version: int,
        dense_dim: int,
        counts: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> None:
        """Stamp the produced export bundle's durable reference (the download endpoint reads this)."""
        async with self._postgres.session() as session:
            await TransferApi.update(
                session,
                transfer_id,
                s3_key=s3_key,
                size_bytes=size_bytes,
                format_version=format_version,
                dense_dim=dense_dim,
                counts=counts,
                expires_at=expires_at,
            )

    async def mark_done(
        self,
        transfer_id: uuid.UUID,
        finished_at: datetime,
        *,
        collection_id: uuid.UUID | None = None,
        collection_name: str | None = None,
        counts: dict[str, Any] | None = None,
    ) -> None:
        """Terminal success — 100%, DONE, and (for import) the new collection's id AND name."""
        async with self._postgres.session() as session:
            await TransferApi.update(
                session,
                transfer_id,
                status=TransferStatus.DONE,
                progress=100,
                finished_at=finished_at,
                collection_id=collection_id,
                collection_name=collection_name,
                counts=counts,
            )

    async def mark_failed(self, transfer_id: uuid.UUID, error: str, finished_at: datetime) -> None:
        """Terminal failure — FAILED with the error in clear."""
        async with self._postgres.session() as session:
            await TransferApi.update(
                session,
                transfer_id,
                status=TransferStatus.FAILED,
                error=error,
                finished_at=finished_at,
            )


__all__ = ["TransferTrackerFacade"]

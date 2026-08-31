# ====== Code Summary ======
# The `collection_transfer` table — one row per collection EXPORT or IMPORT job. Export/import are
# collection-level operations with no document, so they cannot ride the document-scoped `job` table;
# this row is their status surface AND (for export) the durable artifact reference the download
# endpoint reads: the bundle's S3 key, its size, and an expiry the reaper/cleanup can act on. The
# router creates the row PENDING, enqueues the worker task with its id, then polls it; the worker
# task drives it RUNNING → DONE/FAILED and stamps the artifact/counts as it goes.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, TimestampedMixin, UUIDPrimaryKey, value_enum


class TransferKind(StrEnum):
    """Direction of a collection transfer."""

    EXPORT = "export"
    IMPORT = "import"


class TransferStatus(StrEnum):
    """Lifecycle of a collection transfer job."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class CollectionTransfer(Base, UUIDPrimaryKey, TimestampedMixin):
    """An async collection export/import job and (for export) its bundle artifact reference."""

    __tablename__ = "collection_transfer"

    kind: Mapped[TransferKind] = mapped_column(value_enum(TransferKind), nullable=False)
    status: Mapped[TransferStatus] = mapped_column(
        value_enum(TransferStatus), nullable=False, default=TransferStatus.PENDING
    )
    # Export: the SOURCE collection (SET NULL so deleting it does not destroy a finished bundle
    # record). Import: NULL until success, then the id of the NEWLY created collection.
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection.id", ondelete="SET NULL"), nullable=True, index=True
    )
    collection_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Export: the bundle object's key. Import: the input bundle's key.
    s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    format_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dense_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)  # 0-100
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Per-table counts snapshot ({"documents": n, "chunks": m, "points": k, ...}).
    counts: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When the exported bundle object may be garbage-collected (NULL = keep indefinitely).
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["CollectionTransfer", "TransferKind", "TransferStatus"]

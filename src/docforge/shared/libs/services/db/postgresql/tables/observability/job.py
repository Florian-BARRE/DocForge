# ====== Code Summary ======
# The `job` table — one async ingestion job per document run: its status, the worker that claimed it,
# the retry attempt, the current stage and coarse progress, plus timing and any error. Drives the
# jobs API and the live status UI.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from enum import StrEnum

# ====== Third-Party Library Imports ======
from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, TimestampedMixin, UUIDPrimaryKey, value_enum


class JobStatus(StrEnum):
    """State of an ingestion job."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Job(Base, UUIDPrimaryKey, TimestampedMixin):
    """An async ingestion job for one document."""

    __tablename__ = "job"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        value_enum(JobStatus), nullable=False, default=JobStatus.PENDING
    )
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)  # 0–100
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["Job", "JobStatus"]

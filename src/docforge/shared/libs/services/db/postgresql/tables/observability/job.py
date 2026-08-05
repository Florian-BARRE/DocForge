# ====== Code Summary ======
# The `job` table — one async ingestion job per document run: its status, the worker that claimed it,
# the retry attempt, the current stage and coarse progress, plus timing and any error. Drives the
# jobs API and the live status UI.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

# ====== Third-Party Library Imports ======
from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, SmallInteger, String, Text
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
    # Per-document paid text-gen meter: running totals summed from the job's stages as they finish
    # (a document has one active job, so this row IS its lifetime token/cost total).
    total_prompt_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_completion_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    # Per-item counter for the CURRENT fan-out (foreach) root stage: how many child items have
    # finished (items_done) out of the fan-out width (items_total). Both NULL when the current root
    # stage is not a fan-out; reset to NULL when the job leaves a fan-out stage.
    items_done: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    items_total: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # Structured failure breadcrumb (free-text stays in ``error``): the deepest failed node, its kind
    # (family/action label), the failing item index inside a fan-out (NULL outside a fan-out) and the
    # exception class name. All NULL until the job fails.
    failed_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failed_node_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failed_item_index: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)


__all__ = ["Job", "JobStatus"]

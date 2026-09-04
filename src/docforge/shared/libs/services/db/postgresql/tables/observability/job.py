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
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, TimestampedMixin, UUIDPrimaryKey, value_enum


class JobStatus(StrEnum):
    """State of an ingestion job."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    # Terminal state for a job stopped on request: a queued job cancelled before it ran, a running
    # job that honoured a cooperative stop at a stage boundary, or a wedged job force-terminated.
    # "cancelled" (9 chars) exceeds the status column's current VARCHAR(7) — this REQUIRES a migration
    # to widen the column (see the migration handoff), even though value_enum adds no CHECK constraint.
    CANCELLED = "cancelled"

    @classmethod
    def terminal(cls) -> frozenset["JobStatus"]:
        """
        The states after which a job never changes again — nothing more will land.

        The single source of truth for "is this job over?": mark_done/mark_failed refuse to overwrite
        CANCELLED, so all three (DONE, FAILED, CANCELLED) are absorbing. Consumers (the SSE stream's
        stop condition, the cancel helper's already-terminal check) MUST derive from this rather than
        hard-code a subset — a missing CANCELLED here made the job stream poll forever.

        Returns:
            frozenset[JobStatus]: DONE, FAILED and CANCELLED.
        """
        return frozenset({cls.DONE, cls.FAILED, cls.CANCELLED})


class Job(Base, UUIDPrimaryKey, TimestampedMixin):
    """An async ingestion job for one document."""

    __tablename__ = "job"
    # Hot-path indexes for the reaper / active-job scans and the jobs-by-collection listing. Created by
    # migration f2b9d7c4a1e8; declared here so ``--autogenerate`` reconciles them instead of dropping
    # them. ``ix_job_collection_created_at`` is a plain btree composite for the collection-scoped,
    # created-at-descending listing. ``ix_job_status_active`` is a PARTIAL index whose predicate covers
    # only the live rows (``status IN ('pending', 'running')``) the reaper / list_active / queue_depth
    # scan — Alembic's comparator normalises the ``postgresql_where`` predicate and reconciles it
    # cleanly (verified via ``alembic check``), so unlike the grid's functional/GIN indexes it is safe
    # to declare here rather than leave migration-only.
    __table_args__ = (
        Index("ix_job_collection_created_at", "collection_id", text("created_at DESC")),
        Index(
            "ix_job_status_active",
            "status",
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        value_enum(JobStatus), nullable=False, default=JobStatus.PENDING
    )
    # The cooperative-cancel signal: set True to REQUEST a running job stop at its next stage boundary
    # (the job stays RUNNING until the worker honours it, so status-keyed queries — reaper, list_active,
    # queue_depth — are untouched). Also raised by a force-terminate as a backstop stop signal.
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
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

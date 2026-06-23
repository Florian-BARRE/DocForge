# ====== Code Summary ======
# SQLAlchemy ORM model for the async ingestion job record.
# Created at admission time and updated by the pipeline runner (arq workers).

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from sqlalchemy import DateTime, Float, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# ====== Local Project Imports ======
from .base import Base

# Cross-model relationship uses a string class name resolved by the SQLAlchemy registry;
# the import is type-checking only to avoid a runtime circular import.
if TYPE_CHECKING:
    from .document import DocumentModel


class JobModel(Base):
    """
    Async ingestion job record.

    Created at admission time; updated by the pipeline runner (BackgroundTasks in P1,
    arq workers in P2+).
    """

    __tablename__ = "job"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    # status: pending | running | done | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_spent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Observability (Brique A) ──────────────────────────────────────────────
    # Identifier of the worker process that picked up the job (hostname:pid:rand).
    # Nullable: a pending job has not been claimed by any worker yet.
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Wall-clock execution window, set by the worker on running → done/failed.
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # arq retry attempt number (1-based) — surfaces flapping jobs in monitoring.
    attempt: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    # Coarse pipeline progress for live UI: current stage node id + 0–100 percent.
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    # Relationship
    document: Mapped[DocumentModel] = relationship(back_populates="jobs")

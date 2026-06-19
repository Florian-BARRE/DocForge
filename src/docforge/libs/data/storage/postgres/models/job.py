# ====== Code Summary ======
# SQLAlchemy ORM model for the async ingestion job record.
# Created at admission time and updated by the pipeline runner (arq workers).

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
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

    # Relationship
    document: Mapped[DocumentModel] = relationship(back_populates="jobs")

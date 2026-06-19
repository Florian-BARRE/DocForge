# ====== Code Summary ======
# SQLAlchemy ORM model for the Document catalogue record.
# source_hash (sha256) is the content-address of the original file; it drives
# deduplication together with pipeline_version.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

# ====== Third-Party Library Imports ======
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# ====== Local Project Imports ======
from .base import Base

# Cross-model relationships use string class names resolved by the SQLAlchemy registry;
# imports are type-checking only to avoid runtime circular imports.
if TYPE_CHECKING:
    from .block import BlockModel
    from .collection import CollectionModel
    from .job import JobModel


class DocumentModel(Base):
    """
    Catalogue record for an ingested document.

    source_hash (sha256) is the content-address of the original file.
    Deduplication: same source_hash + pipeline_version → no-op (returned as 200).
    """

    __tablename__ = "document"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collection.id", ondelete="CASCADE"), nullable=False
    )
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    user_meta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    implicit_meta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False)
    # status: pending | processing | done | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    collection: Mapped[CollectionModel] = relationship(back_populates="documents")
    blocks: Mapped[list[BlockModel]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[JobModel]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

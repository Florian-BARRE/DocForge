# ====== Code Summary ======
# SQLAlchemy ORM model for the persisted IR block — the granular unit of the
# document tree stored in Postgres. type_data holds type-specific payload
# (table cells, figure crops/OCR/descriptions, etc.).

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

# ====== Third-Party Library Imports ======
from sqlalchemy import ARRAY, JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# ====== Local Project Imports ======
from .base import Base

# Cross-model relationships are declared with string class names and resolved by the
# SQLAlchemy registry at mapper-configuration time; the import is type-checking only
# to keep static analysis happy without creating a runtime circular import.
if TYPE_CHECKING:
    from .document import DocumentModel


class BlockModel(Base):
    """
    Persisted IR block — the granular unit of the document tree stored in Postgres.

    type_data holds type-specific payload:
      - TABLE blocks: cells, n_rows, n_cols, has_header
      - FIGURE blocks: kind, crop_key, relevance, ocr_text, description, data_table
    """

    __tablename__ = "block"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    type_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Relationship
    document: Mapped[DocumentModel] = relationship(back_populates="blocks")

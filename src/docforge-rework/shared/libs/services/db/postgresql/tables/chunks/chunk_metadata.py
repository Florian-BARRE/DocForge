# ====== Code Summary ======
# The `chunk_metadata` table — the metadata VALUES generated PER CHUNK by the metagen (LLM) stage,
# one row per field. Chunk-scope values override the document-scope ones at index time. Same shape
# as `document_metadata`: relational, with a JSONB value typed by the field.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import ForeignKey, Integer, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin

# ====== Local Project Imports ======
from ..base import Base, value_enum


class ChunkMetadata(Base):
    """One generated metadata value of a chunk (chunk-scope)."""

    __tablename__ = "chunk_metadata"
    __table_args__ = (UniqueConstraint("chunk_id", "field_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("chunk.id", ondelete="CASCADE"), nullable=False
    )
    field_id: Mapped[int] = mapped_column(
        ForeignKey("metadata_field.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    origin: Mapped[FieldOrigin] = mapped_column(
        value_enum(FieldOrigin), nullable=False, default=FieldOrigin.GENERATED
    )


__all__ = ["ChunkMetadata"]

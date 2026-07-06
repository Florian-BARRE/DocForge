# ====== Code Summary ======
# The `document_metadata` table — the metadata VALUES of a document, one row per field. Relational
# (not a JSONB map) so values are first-class and queryable in Postgres: which documents have field
# X = Y. The value itself is a JSONB scalar/list (typed by the field). Origin records who filled it
# (user upload / pipeline-extracted / LLM-generated).

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin

# ====== Local Project Imports ======
from ..base import Base, value_enum


class DocumentMetadata(Base):
    """One metadata value of a document (document-scope)."""

    __tablename__ = "document_metadata"
    __table_args__ = (UniqueConstraint("document_id", "field_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    field_id: Mapped[int] = mapped_column(
        ForeignKey("metadata_field.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    origin: Mapped[FieldOrigin] = mapped_column(value_enum(FieldOrigin), nullable=False)


__all__ = ["DocumentMetadata"]

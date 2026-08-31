# ====== Code Summary ======
# The `document_metadata` table — the metadata VALUES of a document, one row per field. Relational
# (not a JSONB map) so values are first-class and queryable in Postgres: which documents have field
# X = Y. The value itself is a JSONB scalar/list (typed by the field). Origin records who filled it
# (user upload / pipeline-extracted / LLM-generated).

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldOrigin

# ====== Local Project Imports ======
from ..base import Base, value_enum


class DocumentMetadata(Base):
    """One metadata value of a document (document-scope)."""

    __tablename__ = "document_metadata"
    # Field-leading composite backing the grid's correlated EXISTS + scalar sort subquery (created by
    # migration c3e9a1f7d2b4). Its two siblings from that migration are intentionally NOT declared
    # here: the functional index ``ix_docmeta_field_value_text`` on
    # ``(field_id, jsonb_extract_path_text(value))`` and the GIN index ``ix_docmeta_value_gin`` on
    # ``value`` both compare unreliably under ``--autogenerate``, so they live migration-only.
    __table_args__ = (
        UniqueConstraint("document_id", "field_id"),
        Index("ix_docmeta_field_document", "field_id", "document_id"),
    )

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

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
    # Read-path indexes created by migration c3e9a1f7d2b4, declared here so ``--autogenerate`` sees
    # them and never proposes a spurious DROP:
    #  - ``ix_docmeta_field_document``: field-leading composite for the grid's correlated EXISTS +
    #    scalar sort subquery.
    #  - ``ix_docmeta_value_gin``: GIN on the raw JSONB ``value`` for list-field containment (has_any).
    #    A plain-column GIN round-trips reliably through autogenerate (``postgresql_using`` matches).
    # The third sibling from that migration — the FUNCTIONAL index ``ix_docmeta_field_value_text`` on
    # ``(field_id, (value #>> '{}'))`` — is NOT declared here: an expression key does not compare
    # reliably under autogenerate (it would churn as drop+recreate). It stays migration-only and is
    # excluded from autogenerate by name in ``shared/migrations/env.py`` (_AUTOGEN_IGNORED_INDEXES).
    __table_args__ = (
        UniqueConstraint("document_id", "field_id"),
        Index("ix_docmeta_field_document", "field_id", "document_id"),
        Index("ix_docmeta_value_gin", "value", postgresql_using="gin"),
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

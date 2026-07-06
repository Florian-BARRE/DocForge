# ====== Code Summary ======
# The `entity_mention` table — named entities extracted from a chunk (dates, amounts, people, orgs,
# …). They feed the collection's `filterable` metadata fields and support entity-aware retrieval.
# The `span` (character offsets / bbox) locates the mention for highlighting.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, CreatedAtMixin, UUIDPrimaryKey


class EntityMention(Base, UUIDPrimaryKey, CreatedAtMixin):
    """A named entity found in a chunk."""

    __tablename__ = "entity_mention"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("chunk.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)  # date | amount | person | org | …
    surface_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    span: Mapped[Any | None] = mapped_column(JSONB, nullable=True)  # char offsets / bbox


__all__ = ["EntityMention"]

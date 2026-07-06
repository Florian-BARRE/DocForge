# ====== Code Summary ======
# The `block` table — the RAW IR from parsing: one row per DocumentIR node. Carries structure (type,
# page, bbox, reading order, column, heading tree) and native text. Table structure and figure crops
# live in their own detail tables; enrichment (OCR/VLM/…) lives in `block_enrichment`. `is_boilerplate`
# flags repeated headers/footers/watermarks found by the cleaning pass.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, CreatedAtMixin


class Block(Base, CreatedAtMixin):
    """One RAW IR block (text / heading / list / code / formula / table / figure)."""

    __tablename__ = "block"

    # Hierarchical, document-namespaced id (e.g. "<doc>:#/texts/0") — unique across documents.
    id: Mapped[str] = mapped_column(String(256), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_type: Mapped[str] = mapped_column(String(32), nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)
    column_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Deferred self-FK: the heading-tree check runs at COMMIT, so bulk inserts never depend on the
    # parent/child ordering of the rows (large documents split across several INSERT statements).
    parent_id: Mapped[str | None] = mapped_column(
        String(256),
        ForeignKey("block.id", ondelete="SET NULL", deferrable=True, initially="DEFERRED"),
        nullable=True,
        index=True,
    )
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_boilerplate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


__all__ = ["Block"]

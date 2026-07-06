# ====== Code Summary ======
# The `block_table` table — the parse-time structure of a TABLE block (TSR output), 1:1 with its
# block. Holds the grid shape, the cells (a 2D grid is genuinely document-shaped → JSONB), and the
# deterministic markdown linearization. Its LLM summary (for embedding) is an ENRICHMENT and lives
# in `block_enrichment` (kind = table_summary), like a figure's OCR/VLM — never duplicated here.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base


class BlockTable(Base):
    """Structure of a TABLE block (1:1 with the block)."""

    __tablename__ = "block_table"

    block_id: Mapped[str] = mapped_column(
        String(256), ForeignKey("block.id", ondelete="CASCADE"), primary_key=True
    )
    n_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    n_cols: Mapped[int] = mapped_column(Integer, nullable=False)
    has_header: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cells: Mapped[Any] = mapped_column(JSONB, nullable=False)  # row-major 2D grid
    linearized_md: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["BlockTable"]

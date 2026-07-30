# ====== Code Summary ======
# The `block_figure` table — the parse-time facts of a FIGURE block, 1:1 with its block: the cropped
# image (referenced in S3 by its blob hash) and the association to its caption block (proximity +
# numbering). The generated content — classification, OCR, VLM description, chart-to-data — is an
# ENRICHMENT and lives in `block_enrichment`, so raw parse and enrichment stay cleanly separated.

# ====== Standard Library Imports ======
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base


class BlockFigure(Base):
    """Parse-time facts of a FIGURE block (1:1 with the block)."""

    __tablename__ = "block_figure"

    block_id: Mapped[str] = mapped_column(
        String(256), ForeignKey("block.id", ondelete="CASCADE"), primary_key=True
    )
    crop_blob_hash: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("blob.content_hash", ondelete="SET NULL"), nullable=True, index=True
    )
    caption_block_id: Mapped[str | None] = mapped_column(
        String(256), ForeignKey("block.id", ondelete="SET NULL"), nullable=True, index=True
    )


__all__ = ["BlockFigure"]

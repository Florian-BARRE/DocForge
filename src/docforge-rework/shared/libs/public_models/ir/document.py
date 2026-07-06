# ====== Code Summary ======
# DocumentIR — the canonical Intermediate Representation, the pivot of the whole pipeline. Every
# downstream stage (enrich, chunk, contextualize, embed) consumes the IR, never the raw source or
# the flat markdown. It is PARSER-AGNOSTIC: any parser (Docling today, MinerU/Marker later) maps its
# own output into this shape, so nothing downstream changes when a parser is added or swapped.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from ..base import Artifact

# ====== Local Project Imports ======
from .block import Block
from .enums import BlockType


class DocumentIR(Artifact):
    """Canonical, parser-agnostic representation of a parsed document — the pipeline's pivot."""

    doc_id: str = Field(description="Unique document identifier.")
    source_hash: str = Field(description="Content-addressing hash of the original file bytes.")
    title: str = Field(default="", description="Parser-extracted title (empty when unavailable).")
    n_pages: int = Field(default=0, description="Total page count.")
    language: str = Field(default="", description="Dominant ISO 639-1 language code.")
    blocks: list[Block] = Field(
        default_factory=list,
        description="All blocks in reading order; the heading tree is encoded via parent_id.",
    )

    @property
    def heading_blocks(self) -> list[Block]:
        """Return the HEADING blocks, in reading order."""
        return [block for block in self.blocks if block.block_type == BlockType.HEADING]

    @property
    def figure_blocks(self) -> list[Block]:
        """Return the FIGURE blocks, in reading order."""
        return [block for block in self.blocks if block.block_type == BlockType.FIGURE]

    @property
    def table_blocks(self) -> list[Block]:
        """Return the TABLE blocks, in reading order."""
        return [block for block in self.blocks if block.block_type == BlockType.TABLE]


__all__ = ["DocumentIR"]

# ====== Code Summary ======
# The atomic unit of the IR: a block carrying its semantic type, physical provenance, absolute
# reading order, heading-tree links, and exactly the content slot its type needs (text | table |
# figure). Parser-agnostic — any parser maps its own element into this shape.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .enums import BlockType
from .figure import FigureEnrichment
from .provenance import Provenance
from .table import TableData


class Block(BaseModel):
    """Atomic unit of the DocumentIR — content, provenance and enrichment slots."""

    id: str = Field(description="Unique block identifier within the document.")
    block_type: BlockType
    provenance: Provenance
    reading_order: int = Field(description="Absolute reading order across all pages (0-indexed).")
    parent_id: str | None = Field(
        default=None, description="Id of the parent HEADING block; builds the heading tree."
    )
    level: int | None = Field(
        default=None, description="Heading depth (1 = H1, 2 = H2, …); only set for HEADING blocks."
    )
    text: str | None = Field(
        default=None, description="Native text content for text-bearing blocks."
    )
    table: TableData | None = Field(
        default=None, description="Structured table; only for TABLE blocks."
    )
    figure: FigureEnrichment | None = Field(
        default=None, description="Figure enrichment; only for FIGURE blocks."
    )
    language: str | None = Field(
        default=None,
        description="ISO 639-1 code when the block differs from the document language.",
    )


__all__ = ["Block"]

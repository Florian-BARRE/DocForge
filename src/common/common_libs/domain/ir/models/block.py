# ====== Code Summary ======
# Block model: atomic unit of the DocumentIR, carrying content, provenance, and enrichment slots.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .chain_trace import ChainTrace
from .enums import BlockType
from .figure_enrichment import FigureEnrichment
from .provenance import Provenance
from .table_data import TableData


class Block(BaseModel):
    """Atomic unit of the DocumentIR.  Carries content, provenance, and enrichment slots."""

    id: str = Field(..., description="Unique block identifier within the document.")
    type: BlockType
    prov: Provenance
    reading_order: int = Field(
        ...,
        description="Absolute reading order across all pages (0-indexed).",
    )
    parent_id: str | None = Field(
        default=None,
        description="ID of the parent HEADING block; builds the heading tree.",
    )
    level: int | None = Field(
        default=None,
        description="Heading depth (1 = H1, 2 = H2, …); only set for HEADING blocks.",
    )
    text: str | None = Field(
        default=None,
        description="Native text content for text-bearing blocks.",
    )
    table: TableData | None = Field(
        default=None,
        description="Structured table data; only set for TABLE blocks.",
    )
    figure: FigureEnrichment | None = Field(
        default=None,
        description="Figure enrichment; only set for FIGURE blocks.",
    )
    language: str | None = Field(
        default=None,
        description="ISO 639-1 language code when the block differs from the document language.",
    )
    chain_traces: list[ChainTrace] = Field(
        default_factory=list,
        description=(
            "Per-stage provider chain attempts that touched THIS block "
            "(classifier / ocr / vlm).  Empty by default so existing IR rows still load."
        ),
    )

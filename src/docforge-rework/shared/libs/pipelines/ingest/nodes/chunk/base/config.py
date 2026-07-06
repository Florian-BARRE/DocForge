# ====== Code Summary ======
# The config every chunking method shares: the COMPOSITION RULES applied by the common IR →
# passages projection (what enters the chunkable text and what must stay whole) plus the
# tokenizer every size decision is measured with. Each method (structure_aware, fixed_size,
# semantic…) extends this with its own splitting knobs.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig


class BaseChunkerConfig(NodeConfig):
    """Shared chunker config — composition rules + tokenizer."""

    tokenizer_encoding: str = Field(
        default="cl100k_base",
        description="tiktoken encoding every token measure uses (chunk sizes drive embedding).",
    )
    include_tables: bool = Field(
        default=True, description="Render tables (markdown) into the chunkable text."
    )
    include_figures: bool = Field(
        default=True,
        description="Inject each figure's meaning (caption + description + OCR text) into the "
        "chunkable text at the figure's position.",
    )
    tables_atomic: bool = Field(
        default=True, description="A table is one unsplittable unit (never cut mid-table)."
    )
    figures_atomic: bool = Field(
        default=True,
        description="A figure and its meaning travel as ONE unsplittable unit.",
    )


__all__ = ["BaseChunkerConfig"]

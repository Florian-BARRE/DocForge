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
    detect_repeated_boilerplate: bool = Field(
        default=True,
        description="Classify passages whose normalized text recurs across many pages as "
        "BOILERPLATE (repeated inter-slide/inter-page furniture); such chunks are kept but "
        "disabled-by-role, exactly like header/footer, so they are never embedded.",
    )
    boilerplate_min_pages: int = Field(
        default=3,
        ge=2,
        description="A text is boilerplate only when its normalized form appears on at least this "
        "many DISTINCT pages (exact-match, conservative). Raise it to demand more repetition.",
    )
    detect_web_chrome: bool = Field(
        default=True,
        description="Classify obvious web-page CHROME (navigation/menu runs, search-widget and "
        "'no results' placeholders dumped from an HTML page) as BOILERPLATE — kept but "
        "disabled-by-role, so it is never embedded nor a search hit. Conservative: only clear "
        "chrome (short runs of many tiny nav labels, or a lone known placeholder) is demoted, "
        "never real prose.",
    )


__all__ = ["BaseChunkerConfig"]

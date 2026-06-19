# ====== Code Summary ======
# HeadingRule and AtomicConfig supporting models for the S4 ChunkConfig.
# These two small models are tightly related (both configure block-level chunking behavior)
# and kept in one file per the tightly-related dataclass exception.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class HeadingRule(BaseModel):
    """
    A regex rule that promotes a matching line of text to a heading at a given level.

    Applied on top of the parser's own heading detection to catch structural titles the
    parser misses (e.g. "ARTICLE 5", "PARTIE I", "ANNEXE A", bold-only titles, numbered
    sections).  Rules are evaluated in order; the first match wins.

    Attributes:
        level (int): Heading level assigned on match (1 = top level).
        pattern (str): Python regex tested against the (stripped) block text.
    """

    level: int = Field(default=1, ge=1, le=8)
    pattern: str


class AtomicConfig(BaseModel):
    """
    Atomic-block policy (spec §4.5 — special blocks): keep semantic units whole.

    Attributes:
        tables (bool): A TABLE is always a single chunk, never split (regardless of size).
        figures (bool): A FIGURE is always its own chunk (OCR + description + chart data).
        formulas (bool): A FORMULA is never separated from the block that introduces it.
        keep_caption_with_figure (bool): An adjacent CAPTION is folded into its FIGURE/TABLE
            chunk instead of drifting into the surrounding text flow.
    """

    tables: bool = True
    figures: bool = True
    formulas: bool = True
    keep_caption_with_figure: bool = True

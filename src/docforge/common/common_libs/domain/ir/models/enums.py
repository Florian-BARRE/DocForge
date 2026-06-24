# ====== Code Summary ======
# BlockType and FigureKind string enumerations for the DocForge IR.
# These two enums are tightly related (both classify IR block content)
# and small enough to share a file per the tightly-related exception.

# ====== Standard Library Imports ======
from enum import StrEnum


class BlockType(StrEnum):
    """Semantic type of a document block."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    FIGURE = "figure"
    CAPTION = "caption"
    CODE = "code"
    FORMULA = "formula"
    HEADER_FOOTER = "header_footer"  # detected, excluded from chunks by default


class FigureKind(StrEnum):
    """Visual category of a figure block, used to route enrichment (OCR / VLM)."""

    SCANNED_TEXT = "scanned_text"  # text rendered as image (scan region)
    CHART = "chart"                # data visualization (bar, line, pie...)
    DIAGRAM = "diagram"            # schema, flow, architecture drawing
    PHOTO = "photo"                # photographic / illustrative content
    DECORATIVE = "decorative"      # logo, banner, separator → skipped by enrichment

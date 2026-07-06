# ====== Code Summary ======
# The two classification enums of the IR: the semantic type of a block, and the visual kind of a
# figure (which routes enrichment). Small and tightly related, so they share one file.

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
    """Visual category of a figure — routes enrichment (OCR / VLM / chart-to-data)."""

    SCANNED_TEXT = "scanned_text"  # text rendered as an image (a scan region)
    CHART = "chart"                # data visualization (bar, line, pie…)
    DIAGRAM = "diagram"            # schema, flow, architecture drawing
    PHOTO = "photo"                # photographic / illustrative content
    DECORATIVE = "decorative"      # logo, banner, separator → skipped by enrichment


__all__ = ["BlockType", "FigureKind"]

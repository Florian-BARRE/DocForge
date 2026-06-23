# ====== Code Summary ======
# DoclingQualityHelpers — static helpers for label mapping and quality/language
# estimation extracted from DoclingIRMapper to keep that file under 200 lines.
#
# Covers: the Docling label → BlockType lookup table, the label-to-block-type
# resolver, and the text-sample builder used for language detection.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Internal Project Imports ======
from libs.domain.ir.models import Block, BlockType


class DoclingQualityHelpers:
    """
    Static helpers for Docling label mapping and document quality estimation.

    Groups the label → BlockType lookup table, the label resolver, and the
    text-sample builder used for language detection.  All methods are pure
    functions — no I/O, no side effects.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[return]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("DoclingQualityHelpers is a static-only class and cannot be instantiated.")

    # Mapping from Docling label strings to canonical BlockType values.
    # Labels come from docling's DocItemLabel enum (.value).
    LABEL_MAP: dict[str, BlockType] = {
        "title": BlockType.HEADING,
        "section_header": BlockType.HEADING,
        "text": BlockType.PARAGRAPH,
        "paragraph": BlockType.PARAGRAPH,
        "list_item": BlockType.LIST_ITEM,
        "table": BlockType.TABLE,
        # Docling 2.x labels images "picture" (the old "figure" label is kept for safety).
        # Charts/figures are also surfaced as pictures and routed to S2 enrichment.
        "picture": BlockType.FIGURE,
        "figure": BlockType.FIGURE,
        "chart": BlockType.FIGURE,
        "caption": BlockType.CAPTION,
        "code": BlockType.CODE,
        "formula": BlockType.FORMULA,
        "page_header": BlockType.HEADER_FOOTER,
        "page_footer": BlockType.HEADER_FOOTER,
    }

    @staticmethod
    def label_to_block_type(label: str) -> BlockType | None:
        """
        Map a Docling element label string to a BlockType, or None to skip.

        Args:
            label (str): Lowercase Docling element label string.

        Returns:
            BlockType | None: Matched block type, or None if label should be skipped.
        """
        return DoclingQualityHelpers.LABEL_MAP.get(label.lower())

    @staticmethod
    def language_sample(blocks: list[Block], max_chars: int = 4000) -> str:
        """
        Concatenate text-bearing blocks (reading order) into a sample for language detection.

        Args:
            blocks (list[Block]): Parsed blocks.
            max_chars (int): Stop once this many characters are gathered (enough to detect).

        Returns:
            str: A text sample, possibly empty when the document carries no extractable text.
        """
        parts: list[str] = []
        total = 0
        for block in blocks:
            if not block.text:
                continue
            parts.append(block.text)
            total += len(block.text)
            if total >= max_chars:
                break
        return " ".join(parts)

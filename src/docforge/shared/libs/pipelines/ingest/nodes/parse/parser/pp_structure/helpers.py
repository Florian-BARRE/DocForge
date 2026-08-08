# ====== Code Summary ======
# Static helpers for the PP-StructureV3 → IR mapping: the sidecar label → BlockType lookup, the
# heading-level synthesis (PP-Structure gives only title vs section, not H1/H2/H3, so levels are
# derived from the label), and the per-block provenance normalization. Provenance is the simple case
# versus docling: PP-Structure bboxes are already PIXELS with a TOP-LEFT origin, so there is NO
# y-flip — the only work is dividing by the rendered page-image dims the sidecar returns. The table
# HTML flattening (the hard part) is delegated to PpStructureTableFlattener.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import BlockType, Provenance, TableData

# ====== Local Project Imports ======
from .table import PpStructureTableFlattener


class PpStructureParseHelpers:
    """Static helpers mapping PP-StructureV3 sidecar blocks into IR components — pure, no side effects."""

    logger = loggerplusplus.bind(identifier="PpStructureParseHelpers")

    # Sidecar block label → canonical BlockType. Unmapped labels (e.g. seal) are skipped.
    LABEL_MAP: dict[str, BlockType] = {
        "doc_title": BlockType.HEADING,
        "title": BlockType.HEADING,
        "paragraph_title": BlockType.HEADING,
        "section_header": BlockType.HEADING,
        "section": BlockType.HEADING,
        "sub_section": BlockType.HEADING,
        "subsection": BlockType.HEADING,
        "text": BlockType.PARAGRAPH,
        "paragraph": BlockType.PARAGRAPH,
        "abstract": BlockType.PARAGRAPH,
        "content": BlockType.PARAGRAPH,
        "reference": BlockType.PARAGRAPH,
        "number": BlockType.PARAGRAPH,
        "list": BlockType.LIST_ITEM,
        "list_item": BlockType.LIST_ITEM,
        "table": BlockType.TABLE,
        "formula": BlockType.FORMULA,
        "image": BlockType.FIGURE,
        "figure": BlockType.FIGURE,
        "chart": BlockType.FIGURE,
        "caption": BlockType.CAPTION,
        "figure_title": BlockType.CAPTION,
        "table_title": BlockType.CAPTION,
        "table_caption": BlockType.CAPTION,
        "header": BlockType.HEADER_FOOTER,
        "footer": BlockType.HEADER_FOOTER,
    }

    # Heading label → absolute level. PP-Structure only distinguishes a document title from section
    # headers, so the tree is flat below level 2 (an accepted limitation shared with granite/rendered
    # PDFs — it only costs breadcrumb depth). Unknown heading labels default to a section (level 2).
    _HEADING_LEVELS: dict[str, int] = {
        "doc_title": 1,
        "title": 1,
        "paragraph_title": 2,
        "section_header": 2,
        "section": 2,
        "sub_section": 3,
        "subsection": 3,
    }

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "PpStructureParseHelpers is a static-only class and cannot be instantiated."
        )

    @classmethod
    def label_to_block_type(cls, label: str) -> BlockType | None:
        """Map a sidecar block label to a BlockType, or None to skip the block."""
        return cls.LABEL_MAP.get(label.strip().lower())

    @classmethod
    def heading_level(cls, label: str) -> int:
        """Synthesize an absolute heading level from a heading label (defaulting a section to 2)."""
        return cls._HEADING_LEVELS.get(label.strip().lower(), 2)

    @staticmethod
    def normalize_bbox(
        bbox: object, image_width: float, image_height: float
    ) -> tuple[float, float, float, float]:
        """
        Normalize a pixel bbox [x0, y0, x1, y1] to [0, 1] using the rendered page-image dims.

        PP-Structure bboxes already use a TOP-LEFT origin, so there is no y-flip — the only work is
        dividing by the page-image dims. Missing/invalid bbox or dims degrade to a full-page box so
        the block still lands on its page rather than being dropped.

        Args:
            bbox (object): The block's ``bbox`` (expected [x0, y0, x1, y1] in pixels).
            image_width (float): Rendered page-image width in pixels (the x divisor).
            image_height (float): Rendered page-image height in pixels (the y divisor).

        Returns:
            tuple[float, float, float, float]: The normalized (x0, y0, x1, y1) clamped to [0, 1].
        """
        # 1. Guard the divisors: a zero/missing dim would blow up or mis-scale every crop.
        width = image_width if image_width and image_width > 0 else 1.0
        height = image_height if image_height and image_height > 0 else 1.0

        # 2. A malformed bbox degrades to the full page rather than dropping the block.
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return (0.0, 0.0, 1.0, 1.0)

        # 3. Divide by the page dims (top-left origin, no flip), order the corners, clamp to [0, 1].
        x0, y0, x1, y1 = (float(value) for value in bbox)
        x0, x1 = x0 / width, x1 / width
        y0, y1 = y0 / height, y1 / height
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)

        def clamp(value: float) -> float:
            return max(0.0, min(1.0, value))

        return (clamp(x0), clamp(y0), clamp(x1), clamp(y1))

    @staticmethod
    def make_provenance(
        bbox: object, page_index: int, image_width: float, image_height: float
    ) -> Provenance:
        """Build a Provenance from a pixel bbox + the page index and rendered page-image dims."""
        return Provenance(
            page=page_index,
            bbox=PpStructureParseHelpers.normalize_bbox(bbox, image_width, image_height),
        )

    @classmethod
    def html_to_table(cls, html: str | None) -> TableData | None:
        """Flatten a table HTML string into a dense row-major TableData (or None on failure)."""
        return PpStructureTableFlattener.html_to_table(html)


__all__ = ["PpStructureParseHelpers"]

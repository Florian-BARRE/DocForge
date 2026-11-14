# ====== Code Summary ======
# The PP-StructureV3 label vocabulary: the sidecar block label → BlockType lookup and the heading-level
# synthesis (PP-Structure gives only title vs section, not H1/H2/H3, so levels are derived from the
# label). PaddleOCR-VL and MinerU emit the SAME pp_structure-style labels, so their mappers reuse
# these tables. The bbox normalization and the HTML-table flattening are shared by all four sidecar
# parsers and live in sidecar_base.

# ====== Internal Project Imports ======
from shared_libs.public_models import BlockType


class PpStructureLabels:
    """The PP-StructureV3 label vocabulary shared by the pp_structure-style sidecar mappers."""

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
    HEADING_LEVELS: dict[str, int] = {
        "doc_title": 1,
        "title": 1,
        "paragraph_title": 2,
        "section_header": 2,
        "section": 2,
        "sub_section": 3,
        "subsection": 3,
    }


__all__ = ["PpStructureLabels"]

# ====== Code Summary ======
# Translates a dots.ocr sidecar response into the canonical DocumentIR — the dots.ocr→IR adapter.
# The dots.ocr sidecar (src/dots_ocr_server, POST /parse) emits the SAME per-page block contract the
# MinerU / PP-StructureV3 / PaddleOCR-VL sidecars do, so the skeleton (page walk, reading order,
# content slots, bbox normalization, table flattening, heading tree) is the shared SidecarIRMapper.
# What is DISTINCT here is the LABEL VOCABULARY: dots.ocr categories (Title, Section-header, List-item,
# Page-header/footer, Picture, Footnote, Caption, Formula, Table, Text) are the model's own taxonomy,
# so this class owns its category→BlockType map + heading-level synthesis (Title=H1,
# Section-header=H2) instead of borrowing pp_structure's.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import BlockType

# ====== Local Project Imports ======
from ..sidecar_base import SidecarIRMapper


class DotsOcrIRMapper(SidecarIRMapper):
    """Static adapter mapping a dots.ocr sidecar response into the canonical DocumentIR.

    Kept a distinct class with its OWN dots.ocr category vocabulary so dots.ocr is its own brick in
    the palette and execution trace.
    """

    logger = loggerplusplus.bind(identifier="DotsOcrIRMapper")
    LOG_LABEL = "dots.ocr"

    # dots.ocr category (lowercased by the sidecar) → canonical BlockType. dots.ocr's taxonomy is:
    # Caption, Footnote, Formula, List-item, Page-footer, Page-header, Picture, Section-header, Table,
    # Text, Title. Unmapped labels are skipped. Page-header/footer are running chrome → HEADER_FOOTER
    # (excluded from chunks by default); Footnote is textual content → PARAGRAPH.
    LABEL_MAP: dict[str, BlockType] = {
        "title": BlockType.HEADING,
        "section-header": BlockType.HEADING,
        "text": BlockType.PARAGRAPH,
        "footnote": BlockType.PARAGRAPH,
        "list-item": BlockType.LIST_ITEM,
        "table": BlockType.TABLE,
        "formula": BlockType.FORMULA,
        "picture": BlockType.FIGURE,
        "caption": BlockType.CAPTION,
        "page-header": BlockType.HEADER_FOOTER,
        "page-footer": BlockType.HEADER_FOOTER,
    }

    # dots.ocr distinguishes only a document Title from a Section-header, so the heading tree is flat
    # below level 2 (an accepted limitation shared with granite/pp_structure — it only costs breadcrumb
    # depth). Unknown heading labels default to a section (level 2).
    HEADING_LEVELS: dict[str, int] = {
        "title": 1,
        "section-header": 2,
    }


__all__ = ["DotsOcrIRMapper"]

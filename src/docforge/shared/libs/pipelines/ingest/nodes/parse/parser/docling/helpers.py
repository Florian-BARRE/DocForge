# ====== Code Summary ======
# Static helpers for the Docling→IR mapping: the Docling label → BlockType lookup and the per-item
# extraction of provenance (page + normalized bbox, converting Docling's bottom-left PDF origin to
# top-left screen coordinates), text, and table cells. All methods are pure functions over Docling
# items typed as Any — no docling import here, so the module loads fine without docling installed
# (only a real parse needs it).

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import BlockType, Provenance, TableData


class DoclingParseHelpers:
    """Static helpers mapping Docling items into IR components — pure, no side effects."""

    logger = loggerplusplus.bind(identifier="DoclingParseHelpers")

    # Docling element label (DocItemLabel.value) → canonical BlockType. Unmapped labels are skipped.
    LABEL_MAP: dict[str, BlockType] = {
        "title": BlockType.HEADING,
        "section_header": BlockType.HEADING,
        "text": BlockType.PARAGRAPH,
        "paragraph": BlockType.PARAGRAPH,
        "list_item": BlockType.LIST_ITEM,
        "table": BlockType.TABLE,
        # Docling 2.x labels images "picture"; charts/figures also surface as pictures.
        "picture": BlockType.FIGURE,
        "figure": BlockType.FIGURE,
        "chart": BlockType.FIGURE,
        "caption": BlockType.CAPTION,
        "code": BlockType.CODE,
        "formula": BlockType.FORMULA,
        "page_header": BlockType.HEADER_FOOTER,
        "page_footer": BlockType.HEADER_FOOTER,
    }

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DoclingParseHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def label_to_block_type(cls, label: str) -> BlockType | None:
        """Map a Docling element label to a BlockType, or None to skip the item."""
        return cls.LABEL_MAP.get(label.lower())

    @staticmethod
    def heading_level(item: Any) -> int:
        """
        Resolve a heading item's absolute nesting level from the Docling item.

        Docling models a document title and its sub-headings on TWO different scales: a ``title``
        item (HTML ``<h1>``) carries NO ``level`` and is the top of the tree, while a
        ``section_header`` item numbers from 1 for the first sub-heading (HTML ``<h2>`` → docling
        level 1, ``<h3>`` → 2, …). Read naively both the title and the first section header land on
        level 1 and flatten into siblings, wrongly nesting every ``<h2>`` under the first one. The
        title occupies level 1, so a section header at docling level N is absolute level N + 1 —
        keeping ``<h1>`` at 1, ``<h2>`` at 2, ``<h3>`` at 3.

        Args:
            item (Any): A Docling heading item (``title`` or ``section_header``).

        Returns:
            int: The absolute heading level (1 for a title, docling level + 1 for a section header).
        """
        raw_level = getattr(item, "level", None)
        return 1 if raw_level is None else int(raw_level) + 1

    @staticmethod
    def extract_provenance(item: Any, docling_doc: Any) -> Provenance | None:
        """
        Extract the page index and a normalized top-left bbox from a Docling item.

        Docling bboxes use a BOTTOM-LEFT origin (PDF convention: y grows upward); this converts to
        TOP-LEFT screen coordinates and normalizes both axes to [0, 1] using the page size.

        Args:
            item (Any): A Docling DocItem carrying a ``prov`` list.
            docling_doc (Any): The parent DoclingDocument, for page-size lookup.

        Returns:
            Provenance | None: Normalized provenance, or None when unavailable.
        """
        try:
            prov_list = getattr(item, "prov", []) or []
            if not prov_list:
                return None
            prov_entry = prov_list[0]
            page_no = prov_entry.page_no  # 1-indexed in Docling
            page_idx = max(0, page_no - 1)  # 0-indexed for the IR
            bbox = prov_entry.bbox

            page_obj = (docling_doc.pages or {}).get(page_no)
            page_size = getattr(page_obj, "size", None) if page_obj else None
            page_w = (getattr(page_size, "width", None) or 1.0) or 1.0
            page_h = (getattr(page_size, "height", None) or 1.0) or 1.0

            # Convert a bottom-left origin to top-left so downstream cropping uses the right region.
            origin = getattr(bbox, "coord_origin", None)
            origin_str = getattr(origin, "value", str(origin)) if origin is not None else ""
            top, bottom = (bbox.t or 0.0), (bbox.b or 0.0)
            if "BOTTOM" in origin_str.upper():
                top_screen, bottom_screen = page_h - top, page_h - bottom
            else:
                top_screen, bottom_screen = top, bottom

            x0 = (bbox.l or 0.0) / page_w
            x1 = (bbox.r or page_w) / page_w
            y0 = top_screen / page_h
            y1 = bottom_screen / page_h
            x0, x1 = min(x0, x1), max(x0, x1)
            y0, y1 = min(y0, y1), max(y0, y1)
            return Provenance(page=page_idx, bbox=(x0, y0, x1, y1))
        except (AttributeError, IndexError, TypeError, ZeroDivisionError):
            return None

    @staticmethod
    def get_text(item: Any) -> str | None:
        """Extract text from a Docling item, preferring get_text() (2.x) then the text attribute.

        get_text() can return empty for natively-parsed html/md items even when ``text`` is set, so
        an empty result falls through to the ``text`` attribute rather than losing the content.
        """
        if hasattr(item, "get_text"):
            try:
                text = item.get_text()
                if text:
                    return text
            except Exception:
                pass
        return getattr(item, "text", None) or None

    @classmethod
    def extract_table(cls, item: Any) -> TableData | None:
        """Extract structured cells from a Docling TableItem's grid model, or None on failure."""
        try:
            if hasattr(item, "data") and item.data:
                grid = item.data.grid
                if not grid:
                    return None
                cells = [[str(cell.text or "") for cell in row] for row in grid]
                n_rows = len(cells)
                n_cols = max((len(row) for row in cells), default=0)
                cls.logger.debug(f"Docling table extracted: {n_rows}x{n_cols}")
                return TableData(cells=cells, n_rows=n_rows, n_cols=n_cols, has_header=n_rows > 1)
        except (AttributeError, TypeError):
            pass
        return None


__all__ = ["DoclingParseHelpers"]

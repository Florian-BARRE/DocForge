# ====== Code Summary ======
# Static extraction helpers for Docling items: provenance (page + normalized bbox),
# raw text retrieval, and table cell extraction from Docling's grid model.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import Provenance, TableData


class DoclingExtractionHelpers:
    """
    Static helpers for extracting structured data from Docling items.

    Covers provenance (page index + normalized bbox), text content, and table cells.
    All methods are pure functions — no instance state, no side effects.
    """

    logger = loggerplusplus.bind(identifier="DoclingExtractionHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Prevent instantiation — this is a static-only helpers class."""
        raise TypeError("DoclingExtractionHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def extract_provenance(item: Any, docling_doc: Any) -> Provenance | None:
        """
        Extract page index and normalized bbox from a Docling item.

        Docling bboxes use BOTTOM-LEFT origin (PDF convention): y grows upward.
        This method converts to TOP-LEFT screen coordinates (y grows downward)
        and normalizes both axes to [0, 1] using the page dimensions.

        Args:
            item: A Docling DocItem carrying a ``prov`` list.
            docling_doc: The parent DoclingDocument (used to look up page size).

        Returns:
            Provenance | None: Normalized provenance, or None if unavailable.
        """
        try:
            prov_list = getattr(item, "prov", []) or []
            if not prov_list:
                return None

            prov_entry = prov_list[0]
            page_no = prov_entry.page_no          # 1-indexed in Docling
            page_idx = max(0, page_no - 1)        # 0-indexed for IR
            bbox = prov_entry.bbox

            # Resolve page dimensions from docling_doc.pages (dict keyed by 1-indexed page_no)
            page_obj = (docling_doc.pages or {}).get(page_no)
            page_size = getattr(page_obj, "size", None) if page_obj else None
            page_w = (getattr(page_size, "width", None) or 1.0) or 1.0
            page_h = (getattr(page_size, "height", None) or 1.0) or 1.0

            # Docling bboxes are often BOTTOM-LEFT origin (PDF convention): y grows upward,
            # so `t` (top edge) > `b` (bottom edge). Convert to TOP-LEFT screen coordinates
            # (y grows downward) so downstream rendering/cropping uses the right region.
            origin = getattr(bbox, "coord_origin", None)
            origin_str = getattr(origin, "value", str(origin)) if origin is not None else ""
            top, bottom = (bbox.t or 0.0), (bbox.b or 0.0)
            if "BOTTOM" in origin_str.upper():
                top_screen = page_h - top         # distance of top edge from the page top
                bottom_screen = page_h - bottom
            else:
                top_screen, bottom_screen = top, bottom

            # Normalize to [0, 1] with y0 < y1 (top-left convention)
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
        """
        Extract text content from a Docling item, preferring the exported text API.

        Tries ``get_text()`` first (Docling 2.x), then falls back to the ``text``
        attribute for compatibility with older versions.

        Args:
            item: A Docling DocItem.

        Returns:
            str | None: Extracted text string, or None if unavailable.
        """
        # Try get_text() first (Docling 2.x API)
        if hasattr(item, "get_text"):
            try:
                return item.get_text() or None
            except Exception:
                pass
        # Fallback to text attribute
        return getattr(item, "text", None) or None

    @classmethod
    def extract_table(cls, item: Any) -> TableData | None:
        """
        Extract structured table cells from a Docling TableItem.

        Reads the ``data.grid`` structure exposed by Docling's TableItem and
        assembles a flat ``TableData`` with cell strings and dimensions.

        Args:
            item: A Docling TableItem carrying a ``data`` attribute with a ``grid``.

        Returns:
            TableData | None: Populated table data, or None if extraction fails.
        """
        try:
            # Docling TableItem exposes export_to_dataframe() or a grid attribute
            if hasattr(item, "data") and item.data:
                grid = item.data.grid
                if not grid:
                    return None
                cells = [
                    [str(cell.text or "") for cell in row]
                    for row in grid
                ]
                n_rows = len(cells)
                n_cols = max(len(r) for r in cells) if cells else 0
                cls.logger.debug(
                    f"DoclingExtractionHelpers: extracted table {n_rows}x{n_cols}"
                )
                return TableData(
                    cells=cells,
                    n_rows=n_rows,
                    n_cols=n_cols,
                    has_header=n_rows > 1,
                )
        except (AttributeError, TypeError):
            pass
        return None

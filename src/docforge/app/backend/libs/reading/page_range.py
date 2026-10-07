# ====== Code Summary ======
# PageRangeParser — parses the reader-facing ``pages`` selector of the document views ("5", "5-7",
# "5,7-9") into a sorted, de-duplicated list of 1-based page numbers, validated against the document's
# page count BEFORE any range is expanded (so "1-999999999" costs nothing). PageRangeError carries a
# caller-facing message (the route maps it to a 422) that always names the document's page count.

# ====== Standard Library Imports ======
import re

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# One selector item: a single page "N" or an inclusive range "A-B" (surrounding spaces tolerated).
_ITEM_PATTERN = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$")


class PageRangeError(ValueError):
    """A ``pages`` selector that is malformed or out of the document's page range."""


class PageRangeParser:
    """Parse and validate a 1-based page selector against a document's page count."""

    logger = loggerplusplus.bind(identifier="PageRangeParser")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("PageRangeParser is a static-only class and cannot be instantiated.")

    @classmethod
    def parse(cls, spec: str, page_count: int) -> list[int]:
        """
        Parse a page selector into the sorted, unique 1-based pages it names.

        Args:
            spec (str): Comma-separated pages and inclusive ranges, e.g. ``"5"``, ``"5-7"``,
                ``"5,7-9"``.
            page_count (int): The document's page count (0 = a page-less document).

        Returns:
            list[int]: The selected pages, ascending, without duplicates.

        Raises:
            PageRangeError: Bad syntax, a 0 page, a reversed range, a page beyond ``page_count``,
                or any selector on a page-less document.
        """
        # 1. A page-less document (HTML, legacy) has nothing to select.
        if page_count <= 0:
            raise PageRangeError(
                "This document has no pages (page-less format or not parsed yet) — omit 'pages' "
                "to read the whole document."
            )

        # 2. Every comma-separated item must be a page or an inclusive range within the document.
        pages: set[int] = set()
        for item in spec.split(","):
            start, end = cls._bounds(item, page_count)
            pages.update(range(start, end + 1))
        return sorted(pages)

    @staticmethod
    def _bounds(item: str, page_count: int) -> tuple[int, int]:
        """Parse one ``N`` / ``A-B`` item into validated inclusive bounds."""
        # 1. Syntax: digits, optionally a dash and more digits.
        valid = f"pages 1-{page_count}"
        match = _ITEM_PATTERN.match(item)
        if match is None:
            raise PageRangeError(
                f"Invalid page selector '{item.strip()}' — use a page ('5'), a range ('5-7') or a "
                f"comma-separated list ('5,7-9'); this document has {page_count} pages ({valid})."
            )

        # 2. Bounds: 1-based, ordered, within the document — checked before any expansion.
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) is not None else start
        if start < 1 or end < start:
            raise PageRangeError(
                f"Invalid page range '{item.strip()}' — pages are 1-based and a range must be "
                f"ascending; this document has {page_count} pages ({valid})."
            )
        if end > page_count:
            raise PageRangeError(
                f"Page {end} is out of range — this document has {page_count} pages ({valid})."
            )
        return start, end


__all__ = ["PageRangeError", "PageRangeParser"]

# ====== Code Summary ======
# IRPageFilter — slices a canonical DocumentIR into one block-subset DocumentIR per selected page, so
# the page-range views can run the UNCHANGED pure linearizer on each page and prefix it with a page
# marker. Selection is by the block's own provenance page (0-based) against the 1-based page numbers a
# reader asks for; the document envelope (title, language, page count) is kept on every slice.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import Block, DocumentIR


class IRPageFilter:
    """Split a DocumentIR into per-page block subsets (pure, no I/O)."""

    logger = loggerplusplus.bind(identifier="IRPageFilter")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("IRPageFilter is a static-only class and cannot be instantiated.")

    @classmethod
    def by_page(cls, ir: DocumentIR, page_numbers: list[int]) -> list[tuple[int, DocumentIR]]:
        """
        Return one (page_number, page-only DocumentIR) pair per requested page, in the given order.

        Args:
            ir (DocumentIR): The whole canonical document.
            page_numbers (list[int]): The 1-based pages to keep (already validated).

        Returns:
            list[tuple[int, DocumentIR]]: Each requested page with the IR restricted to its blocks
            (an empty block list when the page carries none — the caller still marks the page).
        """
        # 1. Bucket the blocks by their 1-based page once (provenance.page is the 0-based index).
        blocks_by_page: dict[int, list[Block]] = {}
        for block in ir.blocks:
            blocks_by_page.setdefault(block.provenance.page + 1, []).append(block)

        # 2. One envelope-preserving copy per requested page, holding only that page's blocks.
        return [
            (page_number, ir.model_copy(update={"blocks": blocks_by_page.get(page_number, [])}))
            for page_number in page_numbers
        ]


__all__ = ["IRPageFilter"]

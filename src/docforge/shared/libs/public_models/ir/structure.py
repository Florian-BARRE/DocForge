# ====== Code Summary ======
# Small document-structure helpers over the IR — the ONE place that knows a table-of-contents
# heading title and how to read a document's fallback title (its first real top-level heading).
# Three call sites shared this logic before (the chunker's role classifier, the doc_meta anchor,
# the persistence title fallback) and drifted; they now all derive from here.

# ====== Standard Library Imports ======
from typing import TYPE_CHECKING

# ====== Local Project Imports ======
from .enums import BlockType

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle at module load
    from .document import DocumentIR

# Conservative, multilingual allow-list of section titles that mark a table-of-contents section,
# matched on the FULL normalized heading text (exact, never substring) so a real section like
# "Table of contributions" is never misread as scaffolding. Extend here — the single source.
TOC_TITLES = frozenset(
    {"contents", "table of contents", "toc", "sommaire", "table des matières", "índice"}
)


def is_toc_title(text: str) -> bool:
    """Whether a heading's text is a known table-of-contents title (furniture, never a real title)."""
    return text.strip().lower() in TOC_TITLES


def first_heading(ir: "DocumentIR") -> str | None:
    """
    The document's first TOP-LEVEL (level-1) heading text — the title fallback when none was parsed.

    Prefers a level-1 heading (the true title); falls back to the first heading of any level when no
    heading is marked level-1 (some parsers omit levels). A table-of-contents heading is skipped —
    it is furniture, never the document's title. Returns None when the document has no heading.

    Args:
        ir (DocumentIR): The document IR to read.

    Returns:
        str | None: The first top-level, non-ToC heading text, or None.
    """
    headings = [
        block
        for block in sorted(ir.blocks, key=lambda block: block.reading_order)
        if block.block_type == BlockType.HEADING
        and block.text
        and block.text.strip()
        and not is_toc_title(block.text)
    ]
    top = next((block for block in headings if block.level == 1), None) or (
        headings[0] if headings else None
    )
    return top.text.strip() if top else None


__all__ = ["TOC_TITLES", "is_toc_title", "first_heading"]

# ====== Code Summary ======
# Serializes a DocumentIR into a faithful flat markdown representation.
# The serialized view is pure structure — NO generated descriptions are injected.
# Figures appear as image references keyed by block_id; enrichment is in the IR, not here.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Local Project Imports ======
from .models import Block, BlockType, DocumentIR


class MarkdownSerializer:
    """
    Converts a DocumentIR into a faithful, structure-preserving markdown string.

    Design rules:
    - Output contains only native text content; VLM descriptions / OCR are NOT embedded.
    - Figures appear as ``![fig:<block_id>](fig:<block_id>)`` — clients resolve via API.
    - Tables are rendered as GFM pipe tables with a header separator row.
    - Heading levels map directly to ``#`` depth.
    - HEADER_FOOTER blocks are excluded.
    """

    def serialize(self, ir: DocumentIR) -> str:
        """
        Produce the faithful markdown view of the IR.

        Args:
            ir (DocumentIR): The parsed and enriched intermediate representation.

        Returns:
            str: A GFM-compatible markdown string with structure preserved.
        """
        # 1. Filter out header/footer blocks — never rendered
        visible = [b for b in ir.blocks if b.type != BlockType.HEADER_FOOTER]

        # 2. Serialize each block in reading order
        parts: list[str] = []
        for block in visible:
            rendered = self._render_block(block)
            if rendered:
                parts.append(rendered)

        # 3. Join with double newlines for GFM paragraph separation
        return "\n\n".join(parts)

    # ─── Private helpers ───────────────────────────────────────────────────────

    def _render_block(self, block: Block) -> str:
        """Dispatch to the appropriate renderer based on block type."""
        dispatch = {
            BlockType.HEADING: self._render_heading,
            BlockType.PARAGRAPH: self._render_paragraph,
            BlockType.LIST_ITEM: self._render_list_item,
            BlockType.TABLE: self._render_table,
            BlockType.FIGURE: self._render_figure,
            BlockType.CAPTION: self._render_caption,
            BlockType.CODE: self._render_code,
            BlockType.FORMULA: self._render_formula,
        }
        renderer = dispatch.get(block.type)
        return renderer(block) if renderer else ""

    def _render_heading(self, block: Block) -> str:
        """Render a heading block with the correct ATX level prefix."""
        level = block.level or 1
        text = block.text or ""
        return f"{'#' * level} {text}"

    def _render_paragraph(self, block: Block) -> str:
        """Render a paragraph block as plain text."""
        return block.text or ""

    def _render_list_item(self, block: Block) -> str:
        """Render a list item with a bullet prefix."""
        return f"- {block.text or ''}"

    def _render_table(self, block: Block) -> str:
        """Render a TABLE block as a GFM pipe table."""
        if block.table is None or not block.table.cells:
            return ""

        rows = block.table.cells
        if not rows:
            return ""

        # 1. Build table lines
        lines: list[str] = []

        # 2. First row becomes the header
        header = rows[0]
        lines.append("| " + " | ".join(self._escape_cell(c) for c in header) + " |")

        # 3. Separator row
        lines.append("| " + " | ".join("---" for _ in header) + " |")

        # 4. Data rows
        for row in rows[1:]:
            lines.append("| " + " | ".join(self._escape_cell(c) for c in row) + " |")

        return "\n".join(lines)

    def _render_figure(self, block: Block) -> str:
        """
        Render a FIGURE block as an image reference keyed by block_id.

        The actual image URL is resolved by the client via GET /chunks/{id} or the
        object-store crop_key.  Enrichment text (OCR, description) is NOT embedded here.
        """
        alt = f"fig:{block.id}"
        return f"![{alt}]({alt})"

    def _render_caption(self, block: Block) -> str:
        """Render a caption as italicized text."""
        return f"_{block.text or ''}_"

    def _render_code(self, block: Block) -> str:
        """Render a code block with a fenced code block."""
        return f"```\n{block.text or ''}\n```"

    def _render_formula(self, block: Block) -> str:
        """Render a formula as a LaTeX display block."""
        return f"$$\n{block.text or ''}\n$$"

    @staticmethod
    def _escape_cell(text: str) -> str:
        """Escape pipe characters inside GFM table cells."""
        return text.replace("|", "\\|")

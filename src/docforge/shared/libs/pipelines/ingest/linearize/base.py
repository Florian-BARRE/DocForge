# ====== Code Summary ======
# BaseIRLinearizer — the shared reading-order WALKER over a canonical DocumentIR. It owns the whole
# structural traversal (sort by reading order, drop detected header/footer boilerplate, fold
# consecutive list items into one list, fold a figure's adjacent caption) and dispatches each logical
# unit to abstract emit hooks. Concrete emitters (markdown, html) only decide how a unit is rendered,
# never how the document is walked — so both views stay structurally identical. PURE: no I/O.

# ====== Standard Library Imports ======
from __future__ import annotations

from abc import ABC, abstractmethod

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.public_models import Block, BlockType, DocumentIR, FigureEnrichment, TableData


class BaseIRLinearizer(ABC, LoggerClass):
    """
    Abstract reading-order walker turning a DocumentIR into a linear document view.

    Subclasses implement the per-unit emit hooks (heading, paragraph, list, table, figure, …); the
    base class owns the single traversal that both the markdown and html views share, so the two can
    never structurally diverge.
    """

    # Segment glue inserted between top-level blocks (overridden per view).
    _block_separator: str = "\n\n"

    def __init__(self) -> None:
        LoggerClass.__init__(self)

    # -------------------- traversal (shared) --------------------
    def render(self, ir: DocumentIR) -> str:
        """
        Walk the IR in reading order and emit the full linear document view.

        Args:
            ir (DocumentIR): The canonical parsed document.

        Returns:
            str: The rendered view (empty string when the document has no renderable block).
        """
        # 1. Reading-order blocks, minus detected header/footer boilerplate (excluded from the view).
        blocks = [
            block
            for block in sorted(ir.blocks, key=lambda item: item.reading_order)
            if block.block_type != BlockType.HEADER_FOOTER
        ]

        # 2. Walk with an explicit cursor so list items and figure captions can be folded ahead.
        segments: list[str] = []
        index = 0
        total = len(blocks)
        while index < total:
            block = blocks[index]
            if block.block_type == BlockType.LIST_ITEM:
                items, index = self.__collect_list_items(blocks, index)
                segments.append(self._emit_list(items))
                continue
            if block.block_type == BlockType.FIGURE:
                caption, index = self.__fold_caption(blocks, index)
                segments.append(self._emit_figure(block.figure, caption, block.text))
                continue
            segments.append(self.__emit_block(block))
            index += 1

        # 3. Join non-empty segments — an emitter returns "" for a unit that carries no content.
        return self._block_separator.join(segment for segment in segments if segment)

    def __collect_list_items(self, blocks: list[Block], start: int) -> tuple[list[str], int]:
        """Gather the run of consecutive LIST_ITEM blocks starting at ``start``."""
        items: list[str] = []
        index = start
        while index < len(blocks) and blocks[index].block_type == BlockType.LIST_ITEM:
            items.append((blocks[index].text or "").strip())
            index += 1
        return items, index

    def __fold_caption(self, blocks: list[Block], start: int) -> tuple[str | None, int]:
        """Consume a FIGURE's immediately-following CAPTION block as the figure caption, if present."""
        next_index = start + 1
        if next_index < len(blocks) and blocks[next_index].block_type == BlockType.CAPTION:
            return (blocks[next_index].text or "").strip() or None, next_index + 1
        return None, next_index

    def __emit_block(self, block: Block) -> str:
        """Dispatch a single (non list-item, non figure) block to its emit hook."""
        block_type = block.block_type
        text = block.text or ""
        if block_type == BlockType.HEADING:
            return self._emit_heading(text.strip(), block.level or 1)
        if block_type == BlockType.TABLE:
            return self._emit_table(block.table) if block.table else ""
        if block_type == BlockType.CAPTION:
            return self._emit_caption(text.strip())
        if block_type == BlockType.CODE:
            return self._emit_code(text)
        if block_type == BlockType.FORMULA:
            return self._emit_formula(text.strip())
        # PARAGRAPH and any future/unknown text-bearing type render as prose.
        return self._emit_paragraph(text.strip())

    # -------------------- emit hooks (per view) --------------------
    @abstractmethod
    def _emit_heading(self, text: str, level: int) -> str:
        """Render a heading at the given level (1-based)."""

    @abstractmethod
    def _emit_paragraph(self, text: str) -> str:
        """Render a paragraph of prose."""

    @abstractmethod
    def _emit_list(self, items: list[str]) -> str:
        """Render a bullet list from its item texts."""

    @abstractmethod
    def _emit_table(self, table: TableData) -> str:
        """Render a structured table."""

    @abstractmethod
    def _emit_figure(
        self, figure: FigureEnrichment | None, caption: str | None, native_text: str | None
    ) -> str:
        """Render a figure: caption, native text and any enrichment (description / OCR / data)."""

    @abstractmethod
    def _emit_caption(self, text: str) -> str:
        """Render a standalone caption block (one not folded into a figure)."""

    @abstractmethod
    def _emit_code(self, text: str) -> str:
        """Render a code block (verbatim)."""

    @abstractmethod
    def _emit_formula(self, text: str) -> str:
        """Render a formula block."""


__all__ = ["BaseIRLinearizer"]

# ====== Code Summary ======
# MarkdownLinearizer — the markdown view of a DocumentIR. It reuses the ONE canonical table renderer
# (ChunkerHelpers.render_table / its markdown grid) for both real tables and chart-to-data grids, so
# a table reads identically in a chunk, in the per-table inspector and in this full-document view.
# PURE: no I/O.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Internal Project Imports ======
from shared_libs.public_models import FigureEnrichment, TableData

# ====== Local Project Imports ======
from ..nodes.chunk.base.helpers import ChunkerHelpers
from .base import BaseIRLinearizer


class MarkdownLinearizer(BaseIRLinearizer):
    """Render a DocumentIR as a coherent full-document markdown view."""

    _block_separator = "\n\n"

    def _emit_heading(self, text: str, level: int) -> str:
        """Render an ATX heading, clamping the level to markdown's 1..6 range."""
        return f"{'#' * max(1, min(level, 6))} {text}" if text else ""

    def _emit_paragraph(self, text: str) -> str:
        """Render a paragraph verbatim."""
        return text

    def _emit_list(self, items: list[str]) -> str:
        """Render a dash bullet list; blank items are dropped."""
        lines = [f"- {item}" for item in items if item]
        return "\n".join(lines)

    def _emit_table(self, table: TableData, caption: str | None) -> str:
        """Render a table via the shared markdown grid, its folded caption in italics above."""
        rendered = ChunkerHelpers.render_table(table)
        if caption:
            return f"*{caption}*\n{rendered}" if rendered else f"*{caption}*"
        return rendered

    def _emit_figure(
        self, figure: FigureEnrichment | None, caption: str | None, native_text: str | None
    ) -> str:
        """
        Render a figure's human-readable content: caption/native prose, then VLM description, OCR
        text and any chart-to-data grid — each on its own paragraph. A content-free figure (a bare
        crop with no enrichment) renders nothing.
        """
        # 1. Caption (folded from the adjacent CAPTION block) and native text are real prose.
        parts: list[str] = []
        header = " ".join(bit for bit in (caption, native_text) if bit and bit.strip())
        if header:
            parts.append(f"*{header.strip()}*")

        # 2. Machine-derived meaning: VLM description, then OCR text.
        if figure and figure.description and figure.description.strip():
            parts.append(figure.description.strip())
        if figure and figure.ocr_text and figure.ocr_text.strip():
            parts.append(figure.ocr_text.strip())

        # 3. Chart-to-data extraction rendered through the same shared grid (first row = header).
        if figure and figure.data_table:
            grid = ChunkerHelpers.render_table(
                TableData(
                    cells=figure.data_table,
                    n_rows=len(figure.data_table),
                    n_cols=max((len(row) for row in figure.data_table), default=0),
                    has_header=True,
                )
            )
            if grid:
                parts.append(grid)

        return "\n\n".join(parts)

    def _emit_caption(self, text: str) -> str:
        """Render a standalone caption in italics."""
        return f"*{text}*" if text else ""

    def _emit_code(self, text: str) -> str:
        """Render a fenced code block."""
        return f"```\n{text}\n```" if text else ""

    def _emit_formula(self, text: str) -> str:
        """Render a formula as a display-math block."""
        return f"$$\n{text}\n$$" if text else ""


__all__ = ["MarkdownLinearizer"]

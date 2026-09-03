# ====== Code Summary ======
# HtmlLinearizer — the structural HTML view of a DocumentIR. It walks the exact same reading order as
# the markdown view (shared base) but emits semantic HTML (h1-h6, p, ul/li, table/thead/tbody/tr/td,
# figure/figcaption, pre/code). Every piece of IR text is HTML-escaped, so parser output can never
# inject markup into the rendered view. PURE: no I/O.

# ====== Standard Library Imports ======
from __future__ import annotations

from html import escape

# ====== Internal Project Imports ======
from shared_libs.public_models import FigureEnrichment, TableData

# ====== Local Project Imports ======
from .base import BaseIRLinearizer


class HtmlLinearizer(BaseIRLinearizer):
    """Render a DocumentIR as a structural, escaped, full-document HTML view."""

    _block_separator = "\n"

    def _emit_heading(self, text: str, level: int) -> str:
        """Render an <h1>..<h6>, clamping the level to the valid range."""
        if not text:
            return ""
        tag = f"h{max(1, min(level, 6))}"
        return f"<{tag}>{escape(text)}</{tag}>"

    def _emit_paragraph(self, text: str) -> str:
        """Render an escaped <p>."""
        return f"<p>{escape(text)}</p>" if text else ""

    def _emit_list(self, items: list[str]) -> str:
        """Render an escaped bullet <ul>; blank items are dropped."""
        cells = [f"<li>{escape(item)}</li>" for item in items if item]
        return f"<ul>{''.join(cells)}</ul>" if cells else ""

    def _emit_table(self, table: TableData) -> str:
        """Render a structured, escaped HTML table (thead when a header row is flagged)."""
        return self.__html_table(table.cells, table.has_header)

    def _emit_figure(
        self, figure: FigureEnrichment | None, caption: str | None, native_text: str | None
    ) -> str:
        """
        Render a <figure>: its enrichment as escaped paragraphs and the caption/native prose as a
        <figcaption>. A content-free figure (bare crop, no enrichment) renders nothing.
        """
        # 1. Enrichment paragraphs: VLM description, OCR text, chart-to-data grid.
        body: list[str] = []
        if figure and figure.description and figure.description.strip():
            body.append(f"<p>{escape(figure.description.strip())}</p>")
        if figure and figure.ocr_text and figure.ocr_text.strip():
            body.append(f"<p>{escape(figure.ocr_text.strip())}</p>")
        if figure and figure.data_table:
            grid = self.__html_table(figure.data_table, has_header=True)
            if grid:
                body.append(grid)

        # 2. Caption + native text become the <figcaption>.
        header = " ".join(bit for bit in (caption, native_text) if bit and bit.strip())
        if header:
            body.append(f"<figcaption>{escape(header.strip())}</figcaption>")

        return f"<figure>{''.join(body)}</figure>" if body else ""

    def _emit_caption(self, text: str) -> str:
        """Render a standalone caption as an emphasized paragraph."""
        return f"<p><em>{escape(text)}</em></p>" if text else ""

    def _emit_code(self, text: str) -> str:
        """Render an escaped <pre><code> block."""
        return f"<pre><code>{escape(text)}</code></pre>" if text else ""

    def _emit_formula(self, text: str) -> str:
        """Render a formula as an escaped paragraph."""
        return f"<p>{escape(text)}</p>" if text else ""

    def __html_table(self, rows: list[list[str]], has_header: bool) -> str:
        """
        Build a semantic HTML table from a row-major grid.

        Cells are escaped and ragged rows are right-padded to the widest row so every ``<tr>`` holds
        the same column count. A degenerate grid (no columns) renders nothing.

        Args:
            rows (list[list[str]]): Row-major cell strings.
            has_header (bool): Emit the first row inside a ``<thead>`` of ``<th>`` cells.

        Returns:
            str: The ``<table>`` markup, or "" for a grid with no columns.
        """
        # 1. Column count from the widest row; nothing to render without columns.
        n_cols = max((len(row) for row in rows), default=0)
        if n_cols == 0:
            return ""

        # 2. Optional header row in a <thead> of <th> cells.
        parts: list[str] = ["<table>"]
        body_rows = rows
        if has_header and rows:
            header_cells = self.__pad(rows[0], n_cols)
            parts.append("<thead><tr>")
            parts.append("".join(f"<th>{escape(cell)}</th>" for cell in header_cells))
            parts.append("</tr></thead>")
            body_rows = rows[1:]

        # 3. Remaining rows in a <tbody> of <td> cells.
        parts.append("<tbody>")
        for row in body_rows:
            cells = self.__pad(row, n_cols)
            parts.append("<tr>")
            parts.append("".join(f"<td>{escape(cell)}</td>" for cell in cells))
            parts.append("</tr>")
        parts.append("</tbody></table>")
        return "".join(parts)

    @staticmethod
    def __pad(row: list[str], n_cols: int) -> list[str]:
        """Right-pad a row with empty cells so it holds exactly ``n_cols`` cells."""
        return list(row) + [""] * (n_cols - len(row))


__all__ = ["HtmlLinearizer"]

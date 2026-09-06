# ====== Code Summary ======
# The HTML-table → TableData flattener for the PP-StructureV3 parser. PP-StructureV3 emits each table
# as an HTML STRING (rowspan/colspan/<thead>), while DocForge's TableData is a FLAT row-major grid
# with no span model. This module parses the HTML with the stdlib html.parser (no new dep) and places
# every cell into its free slots of a dense matrix, EXPANDING spans: the text lands in the top-left
# covered cell and every other covered cell is blank — the repeat-top-left policy that preserves the
# grid shape without inflating token counts. Malformed HTML degrades to None (the block drops its
# table), never a crash.

# ====== Standard Library Imports ======
from dataclasses import dataclass
from html.parser import HTMLParser

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import TableData


@dataclass(slots=True)
class _SpanCell:
    """One parsed HTML cell before span expansion — its text, span, and header flag."""

    text: str = ""
    colspan: int = 1
    rowspan: int = 1
    is_header: bool = False


class _TableCollector(HTMLParser):
    """Stateful html.parser that collects the table's rows as lists of ``_SpanCell`` (pre-expansion).

    Not a LoggerClass: it subclasses the stdlib HTMLParser (whose own __init__ owns the state
    machine); it stays a pure, silent state collector, and the flattener above it owns the logging.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[_SpanCell]] = []
        self.has_header_tag: bool = False
        self._row: list[_SpanCell] | None = None
        self._cell: _SpanCell | None = None
        self._text_parts: list[str] = []
        # Nesting depth of <table> tags. Only the OUTERMOST table (depth 1) contributes rows/cells;
        # a nested table's <tr>/<td> are ignored as structure and their text folds into the enclosing
        # cell, so a table-in-a-cell never corrupts the outer grid.
        self._table_depth: int = 0

    @staticmethod
    def _span(attrs: dict[str, str | None], name: str) -> int:
        """Read a colspan/rowspan attribute as a positive int, defaulting to 1 on anything invalid."""
        try:
            return max(1, int(attrs.get(name) or 1))
        except (TypeError, ValueError):
            return 1

    def _flush_cell(self) -> None:
        """Flush the open cell's accumulated text into the current row, then clear it."""
        if self._cell is not None and self._row is not None:
            self._cell.text = " ".join("".join(self._text_parts).split())
            self._row.append(self._cell)
        self._cell = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Open a row on <tr> or a cell on <td>/<th>, capturing its span attributes."""
        if tag == "table":
            self._table_depth += 1
            return
        if (
            self._table_depth > 1
        ):  # inside a nested table — ignore its structure (text still folds in)
            return
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            if self._row is None:  # a cell outside any <tr> — start an implicit row for it
                self._row = []
            span_attrs = dict(attrs)
            self._cell = _SpanCell(
                colspan=self._span(span_attrs, "colspan"),
                rowspan=self._span(span_attrs, "rowspan"),
                is_header=tag == "th",
            )
            self._text_parts = []
            if tag == "th":
                self.has_header_tag = True

    def handle_data(self, data: str) -> None:
        """Accumulate text while inside a cell (nested-table text included, folded into that cell)."""
        if self._cell is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        """Close the current cell (flush its text) or the current row (append it to ``rows``)."""
        if tag == "table":
            self._table_depth = max(0, self._table_depth - 1)
            return
        if self._table_depth > 1:  # nested-table tags close silently
            return
        if tag in ("td", "th"):
            self._flush_cell()
        elif tag == "tr" and self._row is not None:
            # A row can close with a cell still open (an unclosed <td>): flush it before the row.
            self._flush_cell()
            self.rows.append(self._row)
            self._row = None

    def finalize(self) -> None:
        """Flush any cell/row left dangling by malformed HTML (an unclosed <td> or <tr>).

        Called once after ``feed``/``close``: without it, content of a final unclosed cell or an
        unterminated last row would be silently dropped instead of landing in the grid.
        """
        self._flush_cell()
        if self._row:
            self.rows.append(self._row)
            self._row = None


class PpStructureTableFlattener:
    """Static flattener: an HTML table string → a dense row-major ``TableData`` (or None)."""

    logger = loggerplusplus.bind(identifier="PpStructureTableFlattener")

    # Hard ceiling on the MATERIALIZED grid area (rows × cols). PP-StructureV3 tables come from a
    # sidecar and their rowspan/colspan are untrusted: a malicious/broken cell (e.g. rowspan=1e9)
    # would otherwise expand into an unbounded matrix and hang/OOM the worker. A real page table is
    # orders of magnitude below this, so exceeding it means the table is pathological → skip it.
    MAX_TABLE_CELLS = 200_000

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "PpStructureTableFlattener is a static-only class and cannot be instantiated."
        )

    @classmethod
    def _place(cls, rows: list[list[_SpanCell]]) -> list[list[str]] | None:
        """Place every cell into the next free slots of a dense matrix, expanding row/col spans.

        Args:
            rows (list[list[_SpanCell]]): Parsed rows of pre-expansion cells.

        Returns:
            list[list[str]] | None: A ragged matrix (top-left covered cell holds the text, spanned
                cells blank, not-yet-filled slots ``None``), or None when the span expansion would
                exceed ``MAX_TABLE_CELLS`` — a pathological table is skipped, never materialized.
        """
        matrix: list[list[str | None]] = []

        def ensure(row_idx: int, col_idx: int) -> None:
            while len(matrix) <= row_idx:
                matrix.append([])
            while len(matrix[row_idx]) <= col_idx:
                matrix[row_idx].append(None)

        # 1. For each source row, drop each cell into the first free column, spreading its span.
        for row_idx, row in enumerate(rows):
            ensure(row_idx, 0)
            col = 0
            for cell in row:
                while col < len(matrix[row_idx]) and matrix[row_idx][col] is not None:
                    col += 1
                # A single cell whose span alone blows the ceiling is pathological — bail BEFORE the
                # expansion loop even starts (else a rowspan=1e9 cell iterates a billion times).
                if cell.rowspan * cell.colspan > cls.MAX_TABLE_CELLS:
                    cls.logger.warning(
                        f"PP-Structure table cell span {cell.rowspan}x{cell.colspan} exceeds the "
                        f"{cls.MAX_TABLE_CELLS}-cell cap — skipping the table"
                    )
                    return None
                for delta_row in range(cell.rowspan):
                    for delta_col in range(cell.colspan):
                        target_row, target_col = row_idx + delta_row, col + delta_col
                        # Cumulative bounding-box area guard — many moderate spans can also add up.
                        if (target_row + 1) * (target_col + 1) > cls.MAX_TABLE_CELLS:
                            cls.logger.warning(
                                f"PP-Structure table grid exceeds the {cls.MAX_TABLE_CELLS}-cell "
                                "cap — skipping the table"
                            )
                            return None
                        ensure(target_row, target_col)
                        # Double-booking guard: never overwrite a slot another span already claimed
                        # (a colspan crossing a rowspan reservation in malformed HTML) — the prior
                        # owner keeps the slot, this span just skips it.
                        if matrix[target_row][target_col] is not None:
                            continue
                        top_left = delta_row == 0 and delta_col == 0
                        matrix[target_row][target_col] = cell.text if top_left else ""
                col += cell.colspan

        # 2. Normalise: None → "" and pad every row to the widest so the grid is rectangular.
        n_cols = max((len(row) for row in matrix), default=0)
        return [[value or "" for value in row] + [""] * (n_cols - len(row)) for row in matrix]

    @classmethod
    def html_to_table(cls, html: str | None) -> TableData | None:
        """
        Flatten a PP-StructureV3 table HTML string into a dense row-major TableData.

        Args:
            html (str | None): The table's ``html`` content from the sidecar block.

        Returns:
            TableData | None: The flattened grid, or None when the HTML is empty, has no cells, or
                cannot be parsed (the block then drops its table, as docling does on failure).
        """
        if not html or not html.strip():
            return None
        try:
            collector = _TableCollector()
            collector.feed(html)
            collector.close()
            collector.finalize()  # recover any cell/row left open by malformed HTML
        except Exception as error:  # stdlib parser is lenient; guard the pathological case anyway
            cls.logger.warning(f"PP-Structure table HTML parse failed: {error}")
            return None
        if not collector.rows:
            return None

        cells = cls._place(collector.rows)
        if not cells:
            return None
        n_rows = len(cells)
        n_cols = max((len(row) for row in cells), default=0)
        # An explicit <th>/<thead> is the trusted signal; absent one, a MULTI-COLUMN grid of more than
        # one row is treated as headed (first row = header). A single-column list of rows is not — a
        # vertical enumeration has no header row to promote.
        has_header = collector.has_header_tag or (n_rows > 1 and n_cols > 1)
        cls.logger.debug(f"PP-Structure table flattened: {n_rows}x{n_cols}")
        return TableData(cells=cells, n_rows=n_rows, n_cols=n_cols, has_header=has_header)


__all__ = ["PpStructureTableFlattener"]

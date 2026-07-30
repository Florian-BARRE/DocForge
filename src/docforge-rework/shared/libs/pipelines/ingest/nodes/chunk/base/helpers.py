# ====== Code Summary ======
# Static helpers shared by every chunker: exact token counting (tiktoken, encoders cached
# process-wide), sentence splitting (the sub-passage unit when something must be cut), and the
# markdown rendering of an IR table (what a table contributes to a chunk's text).

# ====== Standard Library Imports ======
import re
import threading
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import FigureEnrichment, TableData

# Sentence boundary: end punctuation followed by whitespace and an uppercase/digit start.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9À-Ü])")

# Any run of whitespace — collapsed to a single space when normalizing text for exact-match compares.
_WHITESPACE_RUN = re.compile(r"\s+")


class ChunkerHelpers:
    """Static utility helpers for the chunker family."""

    logger = loggerplusplus.bind(identifier="ChunkerHelpers")

    # One encoder per encoding name, process-wide (tiktoken loads BPE data on first use).
    _encoders: dict[str, Any] = {}
    _encoders_lock = threading.Lock()

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ChunkerHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def __encoder(cls, encoding_name: str) -> Any:
        """Resolve the encoder once per process (lazy import; the FIRST load may fetch BPE data
        over the network — callers warm it off the event loop, see BaseChunkerNode.run)."""
        with cls._encoders_lock:
            encoder = cls._encoders.get(encoding_name)
            if encoder is None:
                import tiktoken

                encoder = tiktoken.get_encoding(encoding_name)
                cls._encoders[encoding_name] = encoder
        return encoder

    @staticmethod
    def __sanitize_cell(cell: str) -> str:
        """Escape pipes and flatten line breaks so a cell stays within one markdown column."""
        return cell.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    @staticmethod
    def __markdown_grid(rows: list[list[str]], has_header: bool) -> str | None:
        """
        Render a row-major string grid as a markdown table.

        Cells are sanitized (pipes escaped, line breaks flattened) so a value carrying ``|`` or a
        newline — routine in VLM chart-to-data extraction — cannot inject phantom columns or split
        a logical row (which would push the separator mid-table). Ragged rows are right-padded to
        the widest row so the pipe count stays aligned.

        Args:
            rows (list[list[str]]): Row-major cells.
            has_header (bool): Insert a header separator after the first row.

        Returns:
            str | None: The markdown table, or None for a degenerate grid with no columns.
        """
        # 1. Column count from the widest row; a grid with no columns renders nothing.
        n_cols = max((len(row) for row in rows), default=0)
        if n_cols == 0:
            return None
        # 2. Sanitize + right-pad every row so each logical row is exactly n_cols aligned cells.
        lines: list[str] = []
        for row in rows:
            cells = [ChunkerHelpers.__sanitize_cell(cell) for cell in row]
            cells += [""] * (n_cols - len(cells))
            lines.append("| " + " | ".join(cells) + " |")
        # 3. Header separator sits right after the first row when flagged.
        if has_header:
            lines.insert(1, "|" + " --- |" * n_cols)
        return "\n".join(lines)

    @classmethod
    def count_tokens(cls, text: str, encoding_name: str) -> int:
        """
        Count the tokens of a text with the configured tiktoken encoding.

        Args:
            text (str): The text to measure.
            encoding_name (str): tiktoken encoding (e.g. ``cl100k_base``).

        Returns:
            int: Exact token count.
        """
        return len(cls.__encoder(encoding_name).encode(text))

    @classmethod
    def hard_split(cls, text: str, max_tokens: int, encoding_name: str) -> list[str]:
        """
        Token-level cut of a boundary-less text into pieces of at most max_tokens.

        The last resort under a run-on sentence, a URL dump or unsegmented text: when the
        sentence splitter finds no boundary, the size cap must still hold.

        Args:
            text (str): The text to cut.
            max_tokens (int): Hard bound per piece (> 0).
            encoding_name (str): tiktoken encoding.

        Returns:
            list[str]: Pieces of at most max_tokens tokens each.
        """
        # 1. Within bounds → untouched; above → sliced on the token sequence itself.
        encoder = cls.__encoder(encoding_name)
        tokens = encoder.encode(text)
        if len(tokens) <= max_tokens:
            return [text]
        return [
            encoder.decode(tokens[start : start + max_tokens])
            for start in range(0, len(tokens), max_tokens)
        ]

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalize a text for conservative exact-match comparison (repetition / duplicate detection).

        Lowercased, stripped and whitespace-collapsed so that the SAME passage rendered with
        cosmetic spacing differences on two pages still compares equal — the deliberate, minimal
        normalization that keeps repeated-boilerplate and duplicate-heading detection conservative.

        Args:
            text (str): The raw text.

        Returns:
            str: The normalized comparison key (empty when the text is blank).
        """
        return _WHITESPACE_RUN.sub(" ", text.strip().lower())

    @staticmethod
    def split_sentences(text: str) -> list[str]:
        """
        Split a text into sentences — the finest unit a chunker may cut at.

        Args:
            text (str): The text to split.

        Returns:
            list[str]: Non-empty sentences (the whole text when no boundary is found).
        """
        sentences = [part.strip() for part in _SENTENCE_BOUNDARY.split(text)]
        return [sentence for sentence in sentences if sentence] or [text.strip()]

    @staticmethod
    def render_table(table: TableData) -> str:
        """
        Render an IR table as markdown — its textual contribution to a chunk.

        Args:
            table (TableData): The structured table.

        Returns:
            str: A markdown table (with a separator row when a header is flagged).
        """
        return ChunkerHelpers.__markdown_grid(table.cells, table.has_header) or ""

    @staticmethod
    def render_figure(
        figure: FigureEnrichment, caption: str | None, native_text: str | None
    ) -> str | None:
        """
        Render a figure's meaning as an EXPLICITLY MARKED block for the chunkable text.

        A figure's meaning is machine-derived (a VLM description, OCR text): folded into a chunk
        without a marker it reads as if it were a real paragraph of the document. Every part is
        wrapped so a reader — and the retrieval text, which keeps the content verbatim — can tell
        image-derived content from prose. The ``[Image: <kind>]`` and ``[OCR]`` labels are
        structural: kept short and language-neutral (the corpus is multilingual).

        Args:
            figure (FigureEnrichment): The figure slot carrying kind, description and OCR text.
            caption (str | None): The adjacent caption block text, if any.
            native_text (str | None): The figure block's own native text, if any.

        Returns:
            str | None: The marked figure block, or None when the figure carries no content
            (a decorative figure with no caption, description or OCR contributes nothing).
        """
        # 1. Caption + native text are real document prose describing the figure; the marker
        #    frames the whole block as image-derived so the caption cannot pass for a paragraph.
        header_bits = [bit.strip() for bit in (caption, native_text) if bit and bit.strip()]
        header = " ".join([f"[Image: {figure.kind.value}]", *header_bits])
        # 2. The machine-derived meaning, each part labelled distinctly (OCR ≠ description ≠ data).
        lines = [header]
        if figure.description and figure.description.strip():
            lines.append(figure.description.strip())
        if figure.ocr_text and figure.ocr_text.strip():
            lines.append(f"[OCR] {figure.ocr_text.strip()}")
        # 3. Chart-to-data extraction rendered as a marked markdown table (first row = header);
        #    an empty or degenerate grid contributes nothing.
        data_grid = ChunkerHelpers.__markdown_grid(figure.data_table or [], has_header=True)
        if data_grid:
            lines.append("[Data]")
            lines.append(data_grid)
        # 4. A lone marker line means no real content — a decorative figure contributes nothing.
        return "\n".join(lines) if header_bits or len(lines) > 1 else None


__all__ = ["ChunkerHelpers"]

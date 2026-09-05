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
from shared_libs.public_models import Block, BlockType, FigureEnrichment, TableData

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
    def attach_captions(blocks: list[Block]) -> dict[str, Block]:
        """
        Map each FIGURE/TABLE block id to its adjacent CAPTION block — the ONE caption-folding rule.

        Parsers (docling included) emit captions as SEPARATE CAPTION blocks, but the composition rule
        wants the caption INSIDE its figure/table unit. Adjacency in reading order decides ownership:
        the unit right AFTER the caption first, else the one right BEFORE. Each unit claims at most
        one caption. This is the single source of truth shared by the chunker projection and the
        on-the-fly markdown/HTML views, so the two can never fold captions differently.

        Args:
            blocks (list[Block]): The document's blocks in reading order.

        Returns:
            dict[str, Block]: FIGURE/TABLE block id → the CAPTION block folded into it.
        """
        # 1. For every non-empty CAPTION block, claim the adjacent unit after it, else before it.
        attached: dict[str, Block] = {}
        for index, block in enumerate(blocks):
            if block.block_type != BlockType.CAPTION or not (block.text and block.text.strip()):
                continue
            for neighbor_index in (index + 1, index - 1):
                if not 0 <= neighbor_index < len(blocks):
                    continue
                neighbor = blocks[neighbor_index]
                if (
                    neighbor.block_type in (BlockType.FIGURE, BlockType.TABLE)
                    and neighbor.id not in attached
                ):
                    attached[neighbor.id] = block
                    break
        return attached

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
        Render a figure's searchable content for the chunkable text.

        A figure contributes its real prose (caption, native text) plus its machine-derived meaning
        (VLM description, OCR text, extracted data). The machine-derived parts stay labelled
        distinctly (``[OCR]``, ``[Data]``) so they never read as document prose. A content-free
        ``[Image: <kind>]`` marker is DELIBERATELY not emitted: it carries no searchable text, yet a
        chunk assembled with it would match a bare "photo"/"chart" query and self-cite a filename
        with no answer behind it — so the marker is dropped and only real content is rendered.

        Args:
            figure (FigureEnrichment): The figure slot carrying kind, description and OCR text.
            caption (str | None): The adjacent caption block text, if any.
            native_text (str | None): The figure block's own native text, if any.

        Returns:
            str | None: The figure's searchable content, or None when the figure carries none (no
            caption, native text, description, OCR or data). A crop alone is NOT content: it would
            otherwise seed a content-free placeholder chunk that pollutes retrieval.
        """
        # 1. Caption + native text are real document prose describing the figure — kept verbatim.
        header_bits = [bit.strip() for bit in (caption, native_text) if bit and bit.strip()]
        lines: list[str] = []
        if header_bits:
            lines.append(" ".join(header_bits))
        # 2. The machine-derived meaning, each part labelled distinctly (OCR ≠ description ≠ data).
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
        # 4. Emit ONLY when there is real content (caption/native/description/OCR/data). A figure
        #    with a crop but no enrichment (the out-of-box, enrich-off case) contributes nothing
        #    here — the crop still lives on its IR block, reachable via the document view.
        return "\n".join(lines) if lines else None


__all__ = ["ChunkerHelpers"]

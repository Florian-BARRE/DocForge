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
from shared_libs.public_models import TableData

# Sentence boundary: end punctuation followed by whitespace and an uppercase/digit start.
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9À-Ü])")


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
            encoder.decode(tokens[start: start + max_tokens])
            for start in range(0, len(tokens), max_tokens)
        ]

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
        # 1. One markdown row per grid row; the header separator only when flagged.
        lines = ["| " + " | ".join(row) + " |" for row in table.cells]
        if table.has_header and len(lines) >= 1:
            lines.insert(1, "|" + " --- |" * table.n_cols)
        return "\n".join(lines)


__all__ = ["ChunkerHelpers"]

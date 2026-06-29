# ====== Code Summary ======
# SentenceWindowSplitter — sliding-window split method. Segments a section into sentences, then
# emits overlapping windows of N sentences advancing by a stride. Produces dense, overlapping
# context windows (good recall for QA) while tracking every source block a window touches.

# ====== Standard Library Imports ======
from dataclasses import dataclass
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import Block, BlockType

# ====== Local Project Imports ======
from .base import SplitPiece
from ..text_helpers import ChunkingHelpers

# Block types kept whole (one "sentence") rather than sentence-segmented.
_ATOMIC_BLOCK_TYPES = frozenset({BlockType.LIST_ITEM, BlockType.CODE, BlockType.FORMULA})


@dataclass(slots=True)
class _Sentence:
    """A sentence (or atomic unit) paired with the block it came from."""

    text: str
    block_id: str


class SentenceWindowSplitter(LoggerClass):
    """
    Split a section into overlapping fixed-size sentence windows.

    Each window is a piece; consecutive windows overlap by ``window - stride`` sentences, so a
    fact near a window edge still appears whole in a neighbouring window.
    """

    name: str = "sentence_window"

    def __init__(
        self,
        window_sentences: int = 5,
        stride_sentences: int = 4,
        max_tokens: int = 512,
    ) -> None:
        """
        Initialize the sentence-window splitter.

        Args:
            window_sentences (int): Sentences per window (>= 1).
            stride_sentences (int): Sentences advanced between windows (1..window_sentences).
            max_tokens (int): Token budget used by the chunker when packing small sections.
        """
        LoggerClass.__init__(self)
        self._window = max(1, window_sentences)
        self._stride = max(1, min(stride_sentences, self._window))
        self._max_tokens = max_tokens

    @property
    def max_tokens(self) -> int:
        """Token budget per section (packing reference for the chunker)."""
        return self._max_tokens

    def signature(self) -> dict[str, Any]:
        """Return the method id + params for the chunker config hash."""
        return {
            "id": self.name,
            "window_sentences": self._window,
            "stride_sentences": self._stride,
            "max_tokens": self._max_tokens,
        }

    async def split_section(self, blocks: list[Block]) -> list[SplitPiece]:
        """
        Build overlapping sentence windows over the section.

        Args:
            blocks (list[Block]): The section's content blocks in reading order.

        Returns:
            list[SplitPiece]: Ordered (overlapping) window pieces.
        """
        # 1. Flatten the section into a sentence stream tagged with source block ids
        sentences = self._collect_sentences(blocks)
        if not sentences:
            return []

        # 2. A section that fits in one window is a single piece
        if len(sentences) <= self._window:
            return [self._window_piece(sentences)]

        # 3. Slide a fixed window by the stride, stopping once the tail is covered
        pieces: list[SplitPiece] = []
        i = 0
        n = len(sentences)
        while i < n:
            window = sentences[i : i + self._window]
            pieces.append(self._window_piece(window))
            if i + self._window >= n:
                break
            i += self._stride
        return pieces

    # --- Internal -------------------------------------------------------------

    def _collect_sentences(self, blocks: list[Block]) -> list[_Sentence]:
        """Segment each block into sentences (atomic blocks stay whole), tagged with block id."""
        out: list[_Sentence] = []
        for block in blocks:
            if block.type in _ATOMIC_BLOCK_TYPES:
                rendered = ChunkingHelpers.block_to_text(block)
                if rendered.strip():
                    out.append(_Sentence(text=rendered, block_id=block.id))
                continue
            for sent in ChunkingHelpers.split_sentences(block.text or ""):
                out.append(_Sentence(text=sent, block_id=block.id))
        return out

    @staticmethod
    def _window_piece(window: list[_Sentence]) -> SplitPiece:
        """Render a window of sentences into a piece, preserving block-id order without dups."""
        text = " ".join(s.text for s in window)
        seen: dict[str, None] = {}
        for s in window:
            seen.setdefault(s.block_id, None)
        return SplitPiece(text=text, block_ids=list(seen.keys()))


__all__ = ["SentenceWindowSplitter"]

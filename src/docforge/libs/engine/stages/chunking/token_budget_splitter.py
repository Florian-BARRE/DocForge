# ====== Code Summary ======
# TokenBudgetSplitter — the default split method. Greedily packs whole content blocks until the
# token budget would overflow, then starts a new piece (optionally repeating a few trailing
# blocks for overlap). Never breaks immediately before a FORMULA when atomic_formulas is set, so
# a formula stays attached to the block that introduces it.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.core.ir.models import Block, BlockType

# ====== Local Project Imports ======
from .base_splitter import SplitPiece
from .helpers import ChunkingHelpers


class TokenBudgetSplitter(LoggerClass):
    """
    Split a section by packing whole blocks up to a token budget.

    This is the infra-free default: deterministic, fast, and faithful to block boundaries.
    """

    name: str = "token_budget"

    def __init__(
        self,
        max_tokens: int = 512,
        overlap_blocks: int = 0,
        atomic_formulas: bool = True,
    ) -> None:
        """
        Initialize the token-budget splitter.

        Args:
            max_tokens (int): Maximum estimated tokens per piece.
            overlap_blocks (int): Trailing blocks repeated at the start of the next piece.
            atomic_formulas (bool): Never start a new piece right before a FORMULA block.
        """
        LoggerClass.__init__(self)
        self._max_tokens = max_tokens
        self._overlap_blocks = overlap_blocks
        self._atomic_formulas = atomic_formulas

    @property
    def max_tokens(self) -> int:
        """Token budget per piece."""
        return self._max_tokens

    def signature(self) -> dict[str, Any]:
        """Return the method id + params for the S4 config hash."""
        return {
            "id": self.name,
            "max_tokens": self._max_tokens,
            "overlap_blocks": self._overlap_blocks,
            "atomic_formulas": self._atomic_formulas,
        }

    async def split_section(self, blocks: list[Block]) -> list[SplitPiece]:
        """
        Greedily pack blocks into budget-sized pieces, splitting at block boundaries.

        Args:
            blocks (list[Block]): The section's content blocks in reading order.

        Returns:
            list[SplitPiece]: Ordered pieces; one element when the section already fits.
        """
        # 1. Empty section → no pieces
        if not blocks:
            return []

        groups: list[list[Block]] = []
        current: list[Block] = []
        current_tokens = 0

        for block in blocks:
            bt = ChunkingHelpers.estimate_tokens(block)
            # 2. Decide whether this block forces a new piece (budget overflow), but never
            #    break right before a sticky FORMULA — keep it with its introducing block.
            overflow = current and current_tokens + bt > self._max_tokens
            sticky = self._atomic_formulas and block.type == BlockType.FORMULA
            if overflow and not sticky:
                groups.append(current)
                overlap = current[-self._overlap_blocks:] if self._overlap_blocks > 0 else []
                current = list(overlap) + [block]
                current_tokens = sum(ChunkingHelpers.estimate_tokens(b) for b in current)
            else:
                current.append(block)
                current_tokens += bt

        if current:
            groups.append(current)

        # 3. Render each block group into a piece
        return [
            SplitPiece(text=ChunkingHelpers.blocks_to_text(group), block_ids=[b.id for b in group])
            for group in groups
        ]

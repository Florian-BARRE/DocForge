# ====== Code Summary ======
# SemanticSplitter — embedding-based split method. Embeds each block, measures the semantic
# distance between consecutive blocks, and cuts at distance peaks (a configurable percentile),
# so a section breaks where the topic actually shifts rather than at an arbitrary token count.
# Uses the same BGE-M3/TEI embedding model the platform already runs (not an LLM). Falls back to
# a token-budget split if embeddings are unavailable, so chunking never hard-fails.

# ====== Standard Library Imports ======
from __future__ import annotations

import math
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.core.ir.models import Block
from libs.capabilities.embed.base import EmbedProvider

# ====== Local Project Imports ======
from .base_splitter import SplitPiece
from .helpers import ChunkingHelpers


class SemanticSplitter(LoggerClass):
    """
    Split a section at semantic boundaries detected from block embeddings.

    Adjacent blocks are compared by cosine distance; a cut is placed where the distance exceeds
    the ``breakpoint_percentile`` of the section's distances, provided the running piece already
    meets ``min_tokens``. A hard ``max_tokens`` cap always forces a cut so pieces stay bounded.

    The embed provider is the abstract ``EmbedProvider`` Protocol — TEI, OpenAI-compat (local
    or cloud) and any future backend are all interchangeable here.  Boundary detection only
    needs dense vectors, so ``embed_sparse`` is irrelevant for the chosen provider.
    """

    name: str = "semantic"

    def __init__(
        self,
        embed_provider: EmbedProvider,
        max_tokens: int = 512,
        min_tokens: int = 128,
        breakpoint_percentile: int = 90,
    ) -> None:
        """
        Initialize the semantic splitter.

        Args:
            embed_provider (EmbedProvider): Any embedding provider (TEI / openai_compat /
                openai) — only its dense ``embed(texts)`` output is consumed.
            max_tokens (int): Hard cap per piece — a cut is forced before overflow.
            min_tokens (int): A semantic cut is only honoured once the piece reaches this size.
            breakpoint_percentile (int): Distance percentile (50–99) above which a cut is placed.
        """
        LoggerClass.__init__(self)
        self._embed = embed_provider
        self._max_tokens = max_tokens
        self._min_tokens = min_tokens
        self._percentile = max(50, min(99, breakpoint_percentile))

    @property
    def max_tokens(self) -> int:
        """Token budget per piece."""
        return self._max_tokens

    def signature(self) -> dict[str, Any]:
        """Return the method id + params (incl. embed provider id) for the S4 config hash."""
        return {
            "id": self.name,
            "max_tokens": self._max_tokens,
            "min_tokens": self._min_tokens,
            "breakpoint_percentile": self._percentile,
            "embed_provider": getattr(self._embed, "name", "unknown"),
            "embed_version": getattr(self._embed, "version", "0"),
        }

    async def split_section(self, blocks: list[Block]) -> list[SplitPiece]:
        """
        Split the section at embedding-distance peaks (token-budget fallback on failure).

        Args:
            blocks (list[Block]): The section's content blocks in reading order.

        Returns:
            list[SplitPiece]: Ordered pieces.
        """
        # 1. Trivial sections need no boundary detection
        if not blocks:
            return []
        if len(blocks) == 1:
            return [self._piece(blocks)]

        # 2. Embed each block; on any embedding failure, degrade to a token-budget split
        try:
            vectors = await self._embed_blocks(blocks)
        except Exception as exc:  # network / server error — never fail the whole pipeline
            self.logger.warning(f"SemanticSplitter: embedding failed ({exc}); token-budget fallback.")
            return self._token_budget_fallback(blocks)

        # 3. Distances between consecutive blocks → cut threshold at the chosen percentile
        distances = [self._cosine_distance(vectors[i], vectors[i + 1]) for i in range(len(blocks) - 1)]
        threshold = self._percentile_value(distances, self._percentile)

        # 4. Walk blocks, cutting at peaks once min_tokens is met and always before overflow
        groups: list[list[Block]] = []
        current: list[Block] = []
        current_tokens = 0
        for idx, block in enumerate(blocks):
            bt = ChunkingHelpers.estimate_tokens(block)
            if current and current_tokens + bt > self._max_tokens:
                groups.append(current)
                current, current_tokens = [block], bt
                continue
            current.append(block)
            current_tokens += bt
            # Place a semantic cut after this block when the next distance peaks
            is_last = idx == len(blocks) - 1
            if not is_last and current_tokens >= self._min_tokens and distances[idx] >= threshold:
                groups.append(current)
                current, current_tokens = [], 0
        if current:
            groups.append(current)

        return [self._piece(group) for group in groups]

    # ─── Internal ──────────────────────────────────────────────────────────────

    async def _embed_blocks(self, blocks: list[Block]) -> list[list[float]]:
        """Embed each block's rendered text (dense vectors)."""
        texts = [ChunkingHelpers.blocks_to_text([b]) for b in blocks]
        result = await self._embed.embed(texts)
        return result.vectors

    def _token_budget_fallback(self, blocks: list[Block]) -> list[SplitPiece]:
        """Greedy block-budget split used when embeddings are unavailable."""
        groups: list[list[Block]] = []
        current: list[Block] = []
        current_tokens = 0
        for block in blocks:
            bt = ChunkingHelpers.estimate_tokens(block)
            if current and current_tokens + bt > self._max_tokens:
                groups.append(current)
                current, current_tokens = [block], bt
            else:
                current.append(block)
                current_tokens += bt
        if current:
            groups.append(current)
        return [self._piece(group) for group in groups]

    @staticmethod
    def _piece(blocks: list[Block]) -> SplitPiece:
        """Render a block group into a piece."""
        return SplitPiece(
            text=ChunkingHelpers.blocks_to_text(blocks),
            block_ids=[b.id for b in blocks],
        )

    @staticmethod
    def _cosine_distance(a: list[float], b: list[float]) -> float:
        """Return 1 - cosine_similarity(a, b), clamped to [0, 2] (0 = identical)."""
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0.0 or nb == 0.0:
            return 1.0
        return 1.0 - (dot / (na * nb))

    @staticmethod
    def _percentile_value(values: list[float], percentile: int) -> float:
        """Return the value at the given percentile (nearest-rank), or +inf when empty."""
        if not values:
            return float("inf")
        ordered = sorted(values)
        # Nearest-rank: rank = ceil(p/100 * N), 1-indexed.
        rank = max(1, math.ceil(percentile / 100.0 * len(ordered)))
        return ordered[min(rank, len(ordered)) - 1]

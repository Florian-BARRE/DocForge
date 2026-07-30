# ====== Code Summary ======
# The fixed-size chunker — the classic token window: pack passages sequentially into chunks of
# chunk_tokens, IGNORING the document structure, with a configurable overlap repeated between
# consecutive chunks. The baseline method; also the right one for structure-poor documents.

# ====== Third-Party Library Imports ======
from pydantic import Field, model_validator

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..base import BaseChunkerConfig, BaseChunkerNode, Passage


class ChunkerFixedSizeConfig(BaseChunkerConfig):
    """Fixed-window knobs — sizes are token counts of the configured tokenizer."""

    chunk_tokens: int = Field(default=512, gt=0, description="Window size of every chunk.")
    overlap_tokens: int = Field(
        default=64,
        ge=0,
        description="Tail of the previous chunk repeated at the start of the next one.",
    )

    @model_validator(mode="after")
    def check_overlap(self) -> "ChunkerFixedSizeConfig":
        """An overlap as large as the window would never advance — refuse it."""
        if self.overlap_tokens >= self.chunk_tokens:
            raise ValueError("overlap_tokens must be smaller than chunk_tokens")
        return self


@NodeRegistry.register("chunker")
class ChunkerFixedSizeNode(BaseChunkerNode):
    """Pack passages into fixed token windows with overlap, structure-blind."""

    KIND = "fixed_size"
    NAME = "Fixed size"
    SUMMARY = "Classic fixed token windows with overlap, ignoring the document structure."
    HOW_IT_WORKS = (
        "Walks the passages in reading order and packs them into windows of chunk_tokens "
        "(oversized paragraphs cut by sentences; atomic units kept whole), repeating the "
        "previous window's tail as overlap."
    )
    Config = ChunkerFixedSizeConfig
    UNIQUE_IN_GRAPH = True

    async def _split(self, passages: list[Passage]) -> list[list[Passage]]:
        """Explode the oversized, then fill windows sequentially."""
        config: ChunkerFixedSizeConfig = self.config
        # 1. Nothing may exceed the window (atomic units excepted — they stand alone below).
        exploded = [
            sub
            for passage in passages
            for sub in passage.explode(config.chunk_tokens, config.tokenizer_encoding)
        ]

        # 2. Sequential fill; a closed window seeds the next with its overlap tail.
        groups: list[list[Passage]] = []
        current: list[Passage] = []
        current_tokens = 0
        for passage in exploded:
            # 1. An ATOMIC unit bigger than the window stands ALONE — it flushes whatever is
            #    open (an overlap seed included) so nothing gets glued in front of it.
            if passage.token_count > config.chunk_tokens:
                if current:
                    groups.append(current)
                    current, current_tokens = [], 0
                groups.append([passage])
                continue
            # 2. Window full: close and seed the next one with the overlap tail.
            if current and current_tokens + passage.token_count > config.chunk_tokens:
                groups.append(current)
                current = (
                    self._overlap_seed(current, config.overlap_tokens)
                    if config.overlap_tokens
                    else []
                )
                current_tokens = sum(p.token_count for p in current)
            current.append(passage)
            current_tokens += passage.token_count
        if current:
            groups.append(current)
        return groups


__all__ = ["ChunkerFixedSizeNode", "ChunkerFixedSizeConfig"]

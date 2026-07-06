# ====== Code Summary ======
# The structure-aware chunker — packs passages ALONG the heading tree: a section boundary is a
# preferred (or hard) cut, chunks aim at target_tokens, an oversized paragraph is cut by
# sentences, a too-small trailing chunk merges back into its section, and an optional overlap
# repeats the tail of the previous chunk. The go-to method for well-structured documents.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..base import BaseChunkerConfig, BaseChunkerNode, Passage


class ChunkerStructureAwareConfig(BaseChunkerConfig):
    """Structure-aware knobs — sizes are token counts of the configured tokenizer."""

    target_tokens: int = Field(default=512, gt=0, description="Aimed chunk size (soft cap).")
    max_tokens: int = Field(
        default=1024, gt=0, description="Hard cap; a lone non-atomic passage above it is cut."
    )
    min_tokens: int = Field(
        default=64, ge=0, description="Chunks below this merge back into their section."
    )
    overlap_tokens: int = Field(
        default=0,
        ge=0,
        description="When > 0, a new chunk starts with the previous chunk's trailing passages "
        "up to this many tokens (same section only).",
    )
    hard_section_boundaries: bool = Field(
        default=True,
        description="True: a chunk never crosses a section boundary. False: boundaries are "
        "preferred cuts, but small sections may pack together — the chunk then reports the "
        "heading_path of its FIRST passage.",
    )


@NodeRegistry.register("chunker")
class ChunkerStructureAwareNode(BaseChunkerNode):
    """Pack passages along the heading tree into target-sized chunks."""

    KIND = "structure_aware"
    NAME = "Structure-aware"
    SUMMARY = "Chunk along the document's section tree, aiming at a target token size."
    HOW_IT_WORKS = (
        "Walks the passages in reading order and packs them into chunks of ~target_tokens, "
        "cutting at section boundaries (hard or preferred), splitting oversized paragraphs by "
        "sentences, merging too-small section tails, and optionally repeating an overlap tail."
    )
    Config = ChunkerStructureAwareConfig
    UNIQUE_IN_GRAPH = True

    def __pack(self, passages: list[Passage]) -> list[list[Passage]]:
        """The packing walk — sections first, then size."""
        config: ChunkerStructureAwareConfig = self.config
        groups: list[list[Passage]] = []
        current: list[Passage] = []
        current_tokens = 0

        def close(seed_overlap: bool) -> None:
            nonlocal current, current_tokens
            if not current:
                return
            groups.append(current)
            # Overlap only applies to SIZE cuts — a section boundary is a semantic restart.
            current = (
                self._overlap_seed(current, config.overlap_tokens)
                if seed_overlap and config.overlap_tokens
                else []
            )
            current_tokens = sum(passage.token_count for passage in current)

        for passage in passages:
            # 1. Section boundary: a hard cut, or a preferred one once the chunk is big enough.
            if current and passage.section_key != current[-1].section_key:
                if config.hard_section_boundaries or current_tokens >= config.min_tokens:
                    close(seed_overlap=False)

            # 2. An ATOMIC unit bigger than the target stands ALONE — it closes whatever is
            #    open (an overlap seed included) so nothing gets glued in front of it. Only
            #    atomic units can exceed the cap: everything else was exploded/hard-cut.
            if passage.token_count > config.target_tokens:
                close(seed_overlap=False)
                groups.append([passage])
                continue

            # 3. Size: close when adding the passage would overflow the target.
            if current and current_tokens + passage.token_count > config.target_tokens:
                close(seed_overlap=True)

            current.append(passage)
            current_tokens += passage.token_count

        close(seed_overlap=False)
        return groups

    def __merge_small_tails(self, groups: list[list[Passage]]) -> list[list[Passage]]:
        """Merge a too-small group into the previous one when they share a section and fit."""
        config: ChunkerStructureAwareConfig = self.config
        merged: list[list[Passage]] = []
        for group in groups:
            tokens = sum(passage.token_count for passage in group)
            if (
                merged
                and tokens < config.min_tokens
                and group[0].section_key == merged[-1][-1].section_key
                and sum(p.token_count for p in merged[-1]) + tokens <= config.max_tokens
            ):
                merged[-1].extend(group)
                continue
            merged.append(group)
        return merged

    async def _split(self, passages: list[Passage]) -> list[list[Passage]]:
        """Explode the oversized, pack along the tree, merge the small tails."""
        config: ChunkerStructureAwareConfig = self.config
        # 1. Nothing a chunk contains may exceed the hard cap (atomic units excepted).
        exploded = [
            sub
            for passage in passages
            for sub in passage.explode(config.max_tokens, config.tokenizer_encoding)
        ]
        # 2. Pack, then absorb the too-small section tails.
        return self.__merge_small_tails(self.__pack(exploded))


__all__ = ["ChunkerStructureAwareNode", "ChunkerStructureAwareConfig"]

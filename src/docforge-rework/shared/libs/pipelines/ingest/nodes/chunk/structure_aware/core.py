# ====== Code Summary ======
# The structure-aware chunker — packs passages ALONG the heading tree: a section boundary is a
# preferred (or hard) cut, chunks aim at target_tokens, an oversized paragraph is cut by
# sentences, consecutive sub-min_tokens sections are coalesced across boundaries toward the
# target (so a swarm of tiny sections never yields a swarm of tiny chunks), and an optional
# overlap repeats the tail of the previous chunk. The go-to method for well-structured documents.

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
        default=64,
        ge=0,
        description="A section below this is a fragment: consecutive fragments coalesce across "
        "boundaries up to min(target,max). A section at or above it stands alone.",
    )
    overlap_tokens: int = Field(
        default=0,
        ge=0,
        description="When > 0, a new chunk starts with the previous chunk's trailing passages "
        "up to this many tokens (same section only).",
    )
    hard_section_boundaries: bool = Field(
        default=True,
        description="True: a chunk never crosses a section boundary DURING packing — but "
        "consecutive sub-min_tokens sections are still coalesced afterwards (a swarm of tiny "
        "fragments is never desirable). False: boundaries are only preferred cuts. Either way, a "
        "coalesced chunk reports the COMMON heading_path prefix of its passages.",
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
        "sentences, coalescing consecutive sub-min_tokens sections across boundaries toward the "
        "target (a real section stands alone), and optionally repeating an overlap tail."
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

    def __coalesce_small(self, groups: list[list[Passage]]) -> list[list[Passage]]:
        """
        Coalesce consecutive below-min_tokens groups toward target_tokens.

        Under hard boundaries the packing walk emits one group per section, so a document made of
        many tiny adjacent sections yields a swarm of sub-min_tokens chunks. This pass greedily
        folds each such fragment into an open run THAT ITSELF STARTED FROM A FRAGMENT — ACROSS
        section boundaries — while room toward target_tokens remains, never breaching max_tokens.
        A run that started from a real section (>= min_tokens) never absorbs anything, and a real
        section is never absorbed, so well-separated real sections keep their clean cuts.

        Args:
            groups (list[list[Passage]]): The packed groups, in reading order.

        Returns:
            list[list[Passage]]: Fewer groups — tiny fragments coalesced, real sections intact.
        """
        config: ChunkerStructureAwareConfig = self.config
        # 1. Never let coalescing breach the hard cap; target is the soft goal fragments trend to.
        merge_cap = min(config.target_tokens, config.max_tokens)
        coalesced: list[list[Passage]] = []
        running = 0
        # The open run may absorb fragments ONLY when it was itself opened by a fragment — a real
        # section (>= min_tokens) opens a non-absorbing run, so `[A=100, B=30]` keeps B separate.
        tail_is_fragment_run = False
        for group in groups:
            tokens = sum(passage.token_count for passage in group)
            is_fragment = tokens < config.min_tokens
            # 2. A fragment folds into a fragment-born run while room toward the target remains —
            #    the only way a chunk crosses a section boundary here.
            if coalesced and tail_is_fragment_run and is_fragment and running + tokens <= merge_cap:
                coalesced[-1].extend(group)
                running += tokens
                continue
            coalesced.append(group)
            running = tokens
            tail_is_fragment_run = is_fragment
        return coalesced

    async def _split(self, passages: list[Passage]) -> list[list[Passage]]:
        """Explode the oversized, pack along the tree, coalesce the tiny fragments."""
        config: ChunkerStructureAwareConfig = self.config
        # 1. Nothing a chunk contains may exceed the hard cap (atomic units excepted).
        exploded = [
            sub
            for passage in passages
            for sub in passage.explode(config.max_tokens, config.tokenizer_encoding)
        ]
        # 2. Pack along the tree, then coalesce the too-small sections toward the target.
        return self.__coalesce_small(self.__pack(exploded))


__all__ = ["ChunkerStructureAwareNode", "ChunkerStructureAwareConfig"]

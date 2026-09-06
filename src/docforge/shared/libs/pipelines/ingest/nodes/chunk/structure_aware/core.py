# ====== Code Summary ======
# The structure-aware chunker — packs passages ALONG the heading tree: a section boundary is a
# preferred (or hard) cut, chunks aim at target_tokens, an oversized paragraph is cut by
# sentences, consecutive sub-min_tokens HEADING-LESS fragments are coalesced across boundaries
# toward the target (a titled section stands alone whatever its size, so it stays citable), and an
# optional overlap repeats the tail of the previous chunk. The go-to for well-structured documents.

# ====== Third-Party Library Imports ======
from pydantic import Field, model_validator

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
        description="A HEADING-LESS group below this is a fragment: consecutive fragments coalesce "
        "across boundaries up to min(target,max). A titled section (or a group at or above this) "
        "stands alone whatever its size, so a short titled clause stays its own citable chunk.",
    )
    overlap_tokens: int = Field(
        default=64,
        ge=0,
        description="When > 0, a chunk produced by a SIZE cut starts with the previous chunk's "
        "trailing passages up to this many tokens — so a fact split across the cut survives in at "
        "least one chunk. Applies ONLY when a section overflows target_tokens and is split by size; "
        "a section-boundary cut is a semantic restart and never overlaps. Under the default "
        "hard_section_boundaries the previous chunk is single-section, so the repeated tail stays "
        "within one section; with hard_section_boundaries off a size-cut chunk may span sections and "
        "the tail then follows the chunk, not a section. Documents whose sections fit under the "
        "target are unaffected (0 chunks change).",
    )
    hard_section_boundaries: bool = Field(
        default=True,
        description="True: a chunk never crosses a section boundary DURING packing — but "
        "consecutive sub-min_tokens HEADING-LESS fragments are still coalesced afterwards (a swarm "
        "of tiny fragments is never desirable; a titled section always stands alone). False: "
        "boundaries are only preferred cuts. Either way, a coalesced chunk reports the COMMON "
        "heading_path prefix of its passages.",
    )

    @model_validator(mode="after")
    def check_overlap(self) -> "ChunkerStructureAwareConfig":
        """An overlap as large as the HARD cap would never advance a size cut — refuse it.

        Mirrors the fixed-size chunker's guard, bounded against ``max_tokens`` (the hard cap a chunk
        can reach) rather than ``target_tokens`` (the soft goal): only ``max_tokens`` limits how much a
        size-cut chunk can hold, so an ``overlap_tokens`` at or above it could seed a full chunk of pure
        repeat with no room for new content — no forward progress. A small ``target_tokens`` under the
        default overlap stays legal (the overlap tail is still bounded by the chunk's real content).
        """
        if self.overlap_tokens >= self.max_tokens:
            raise ValueError("overlap_tokens must be smaller than max_tokens")
        return self


@NodeRegistry.register("chunker")
class ChunkerStructureAwareNode(BaseChunkerNode):
    """Pack passages along the heading tree into target-sized chunks."""

    KIND = "structure_aware"
    NAME = "Structure-aware"
    SUMMARY = "Chunk along the document's section tree, aiming at a target token size."
    HOW_IT_WORKS = (
        "Walks the passages in reading order and packs them into chunks of ~target_tokens, "
        "cutting at section boundaries (hard or preferred), splitting oversized paragraphs by "
        "sentences, coalescing consecutive sub-min_tokens HEADING-LESS fragments across boundaries "
        "toward the target (a titled section stands alone), and optionally repeating an overlap tail."
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

    @staticmethod
    def __is_titled_section(group: list[Passage]) -> bool:
        """True when the group is a titled section — any passage carries a real (non-blank) heading.

        A titled leaf section is a citable semantic unit: a reader must be able to point at it. A
        DISTINCT top-level titled section therefore stands on its own even when short. Tiny titled
        SIBLING sub-sections under one shared parent are the exception — they coalesce toward the
        target (see ``__coalesce_small``). Genuinely heading-less material is always fragment-coalescible.
        """
        return any(heading.strip() for passage in group for heading in passage.heading_path)

    @staticmethod
    def __parent_key(group: list[Passage]) -> tuple[str, ...]:
        """The group section's PARENT identity — its section_key minus the leaf (``()`` at top level).

        Two tiny titled sub-sections are siblings under one heading exactly when they share this
        non-empty parent key (identity by heading id, so two sections sharing a title never merge by
        accident). A top-level section has an empty parent key and so never joins a sibling run.
        """
        key = group[0].section_key
        return tuple(key[:-1])

    def __coalesce_small(self, groups: list[list[Passage]]) -> list[list[Passage]]:
        """
        Coalesce consecutive below-min_tokens groups toward target_tokens — two coalescing runs.

        The packing walk emits one group per section, which over-fragments a list/enumeration whose
        every item is a titled sub-section (an "11 fields of expertise" list → 11 ~30-token chunks).
        Two kinds of run are folded here, each toward ``min(target, max)`` tokens and never breaching
        ``max_tokens``:

        1. HEADING-LESS fragments — genuinely title-less micro-blocks fold into a fragment-born run
           across boundaries (a swarm of tiny title-less fragments is never desirable).
        2. Tiny titled SIBLING sub-sections — consecutive below-min titled sections that share the
           SAME NON-EMPTY parent heading fold into a sibling-born run (a list under one heading),
           each merged section's own title later inlined by the base so it stays citable.

        A DISTINCT top-level titled section (an Article, a glossary term — empty parent key) and a
        real-sized section still stand ALONE: they neither open an absorbing run nor join one.

        Args:
            groups (list[list[Passage]]): The packed groups, in reading order.

        Returns:
            list[list[Passage]]: Fewer groups — heading-less fragments and tiny same-parent titled
            siblings coalesced; distinct top-level and real-sized sections left intact.
        """
        config: ChunkerStructureAwareConfig = self.config
        # Never let coalescing breach the hard cap; target is the soft goal fragments trend to.
        merge_cap = min(config.target_tokens, config.max_tokens)
        coalesced: list[list[Passage]] = []
        running = 0
        # The kind of run currently open (None = a non-absorbing section) and, for a sibling run,
        # the shared parent it absorbs under. A run only absorbs groups of its OWN kind.
        open_kind: str | None = None
        open_parent: tuple[str, ...] = ()
        for group in groups:
            tokens = sum(passage.token_count for passage in group)
            tiny = tokens < config.min_tokens
            titled = self.__is_titled_section(group)
            parent = self.__parent_key(group)
            fits = coalesced and running + tokens <= merge_cap
            # 1. A heading-less fragment folds into a fragment-born run.
            if fits and open_kind == "fragment" and tiny and not titled:
                coalesced[-1].extend(group)
                running += tokens
                continue
            # 2. A tiny titled sub-section folds into a sibling-born run under the SAME parent.
            if fits and open_kind == "sibling" and tiny and titled and parent == open_parent:
                coalesced[-1].extend(group)
                running += tokens
                continue
            # 3. A new run: it can ABSORB only if it opens as a heading-less fragment or as a tiny
            #    titled sub-section with a real (non-top-level) parent; anything else is non-absorbing.
            coalesced.append(group)
            running = tokens
            if tiny and not titled:
                open_kind, open_parent = "fragment", ()
            elif tiny and titled and parent:
                open_kind, open_parent = "sibling", parent
            else:
                open_kind, open_parent = None, ()
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
        # 2. Pack along the tree, then coalesce the too-small heading-less fragments toward target.
        return self.__coalesce_small(self.__pack(exploded))


__all__ = ["ChunkerStructureAwareNode", "ChunkerStructureAwareConfig"]

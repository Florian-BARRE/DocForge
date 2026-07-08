# ====== Code Summary ======
# BaseChunkerNode — the abstract base of every chunking method. The shared frame: project the
# enriched IR into passages (the composition rules, applied ONCE for all methods), hand them to
# the method's `_split` hook (which only decides the GROUPING), then finalise every group into a
# Chunk (id, ordinal, joined text, block union, token recount, section, page span). A method is
# thus ~one algorithm, nothing else.

# ====== Standard Library Imports ======
import asyncio
from abc import abstractmethod

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode
from shared_libs.public_models import Chunk, DocumentIR

# ====== Local Project Imports ======
from .config import BaseChunkerConfig
from .helpers import ChunkerHelpers
from .io import ChunkerConsumes, ChunkerProduces
from .passages import Passage, PassageProjector


class BaseChunkerNode(ActionNode):
    """Abstract chunking method: passages in, passage GROUPS out; the base does the rest."""

    Consumes = ChunkerConsumes
    Produces = ChunkerProduces

    @abstractmethod
    async def _split(self, passages: list[Passage]) -> list[list[Passage]]:
        """Group the ordered passages into chunks-to-be — the method's whole personality."""
        ...

    def _overlap_seed(self, group: list[Passage], overlap_tokens: int) -> list[Passage]:
        """
        The trailing passages of a closed group that seed the next one (overlap).

        Args:
            group (list[Passage]): The group just closed.
            overlap_tokens (int): Token budget the repeated tail may use.

        Returns:
            list[Passage]: The tail passages fitting the budget, in reading order.
        """
        seed: list[Passage] = []
        taken = 0
        for passage in reversed(group):
            if taken + passage.token_count > overlap_tokens:
                break
            seed.insert(0, passage)
            taken += passage.token_count
        return seed

    @staticmethod
    def __common_heading_path(group: list[Passage]) -> list[str]:
        """
        The heading_path all passages in a group share — their common section ancestry.

        A single-section group returns that section's exact path (every passage shares it). A
        coalesced multi-section group returns only the shared ancestor prefix — `[]` when the
        sections are unrelated (e.g. sibling level-1 sections) — so the chunk never falsely claims
        to live under the first passage's section. Ancestry is compared by section_key IDENTITY
        (heading ids), not by heading TEXT, since two distinct sections may share a title.

        Args:
            group (list[Passage]): The passages of one chunk-to-be, in reading order.

        Returns:
            list[str]: The common heading-path prefix (texts), top-down.
        """
        # 1. Shrink a shared depth down to the shortest common section_key prefix in the group.
        reference = group[0]
        depth = len(reference.section_key)
        for passage in group[1:]:
            common = 0
            for ref_id, other_id in zip(reference.section_key, passage.section_key):
                if ref_id != other_id:
                    break
                common += 1
            depth = min(depth, common)
            if depth == 0:
                break
        # 2. Project that identity depth onto the first passage's heading TEXTS.
        return reference.heading_path[:depth]

    def __finalize(self, ir: DocumentIR, groups: list[list[Passage]]) -> list[Chunk]:
        """Turn each passage group into a Chunk."""
        config: BaseChunkerConfig = self.config
        chunks: list[Chunk] = []
        for group in groups:
            if not group:
                continue
            # 1. Join the group's text; recount on the FINAL text (joins add tokens).
            text = "\n\n".join(passage.text for passage in group)
            # 2. Union of blocks in reading order, deduplicated (overlap may repeat passages).
            block_ids = list(dict.fromkeys(bid for passage in group for bid in passage.block_ids))
            chunks.append(
                Chunk(
                    chunk_id=f"{ir.doc_id}#c{len(chunks)}",
                    ordinal=len(chunks),
                    text=text,
                    block_ids=block_ids,
                    token_count=ChunkerHelpers.count_tokens(text, config.tokenizer_encoding),
                    heading_path=self.__common_heading_path(group),
                    page_start=min(passage.page_start for passage in group),
                    page_end=max(passage.page_end for passage in group),
                )
            )
        return chunks

    async def run(self, data: ChunkerConsumes) -> ChunkerProduces:
        """
        Chunk the enriched IR with this method.

        Args:
            data (ChunkerConsumes): The ENRICHED IR.

        Returns:
            ChunkerProduces: The raw chunks, in reading order.
        """
        # 1. Warm the tokenizer OFF the event loop — its first load may fetch BPE data over the
        #    network, which must never block the loop nor fail mid-projection.
        config: BaseChunkerConfig = self.config
        await asyncio.to_thread(ChunkerHelpers.count_tokens, "", config.tokenizer_encoding)

        # 2. The shared projection: composition rules applied once, whatever the method.
        passages = PassageProjector.project(data.ir, config)
        if not passages:
            self.logger.warning(f"Document '{data.ir.doc_id}' projected to zero passages")
            return ChunkerProduces(chunks=[])

        # 3. The method decides the grouping.
        groups = await self._split(passages)

        # 4. Finalise into chunks. NOTE: caps are SOFT at the join margin — packing sums the
        #    passages' counts, and the "\n\n" joins add a few tokens; token_count is the honest
        #    recount on the final text.
        chunks = self.__finalize(data.ir, groups)
        self.logger.info(
            f"Chunked '{data.ir.doc_id}': {len(passages)} passage(s) -> {len(chunks)} chunk(s)"
        )
        return ChunkerProduces(chunks=chunks)


__all__ = ["BaseChunkerNode"]

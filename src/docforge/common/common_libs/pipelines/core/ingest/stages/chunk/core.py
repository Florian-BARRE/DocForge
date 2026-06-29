# ====== Code Summary ======
# IngestStageChunk — the chunk stage of the ingest pipeline (StageKey.CHUNK). It owns a single step
# (structure-aware chunking) built around a constructor-injected chunking engine whose splitter +
# heading rules + atomic policy + flat/hierarchical mode are assembly-time choices. IDEMPOTENT_WRITE:
# chunk ids are deterministic (UUID5 of doc_id + block_ids + config_hash + ordinal) and the Postgres
# upsert is idempotent, so the stage is never node-cached.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from common_libs.config.pipeline import AtomicConfig
from common_libs.pipelines import CachePolicy, NodeOutput, StageKey, StageSpec

# ====== Local Project Imports ======
from ..base import IngestStageBase
from .context import IngestStageChunkContext
from .errors import IngestStageChunkError
from .io import IngestStageChunkInput, IngestStageChunkOutput
from .steps import IngestStageChunkStepChunk
from .steps.chunk.chunker import SectionSplitter, StructureAwareChunker


class IngestStageChunk(IngestStageBase):
    """
    Chunk stage — split the enriched IR into retrieval chunks via its single chunk step.

    Declares the chunk contract (identity / IO / cache policy) and assembles its step around a
    structure-aware chunking engine built from the stage's constructor-injected configuration.
    """

    SPEC = StageSpec(
        key=StageKey.CHUNK,
        name="Chunk",
        description=(
            "Split the enriched IR into retrieval chunks using heading-hierarchy-aware, "
            "structure-aware chunking."
        ),
        cache_policy=CachePolicy.IDEMPOTENT_WRITE,
    )
    Input = IngestStageChunkInput
    Output = IngestStageChunkOutput
    Context = IngestStageChunkContext
    Error = IngestStageChunkError

    def __init__(
        self,
        *,
        splitter: SectionSplitter | None = None,
        heading_rules: list[Any] | None = None,
        reinject_breadcrumb: bool = True,
        merge_short_sections: bool = True,
        atomic: AtomicConfig | None = None,
        cross_references: bool = True,
        hierarchical: bool = False,
    ) -> None:
        """
        Build the chunking engine from the assembly-time configuration and wire the single step.

        Args:
            splitter (SectionSplitter | None): Intra-section split method. None -> a default
                TokenBudgetSplitter.
            heading_rules (list | None): Ordered HeadingRule-like objects promoting text to headings.
            reinject_breadcrumb (bool): Record the section breadcrumb on each chunk.
            merge_short_sections (bool): Pack small sibling sections together (flat mode only).
            atomic (AtomicConfig | None): Atomic-block policy (tables/figures/formulas/captions).
            cross_references (bool): Run the cross-reference linking pass.
            hierarchical (bool): Emit a parent chunk per divided section over its children.
        """
        super().__init__()
        chunker = StructureAwareChunker(
            splitter=splitter,
            heading_rules=heading_rules,
            reinject_breadcrumb=reinject_breadcrumb,
            merge_short_sections=merge_short_sections,
            atomic=atomic,
            cross_references=cross_references,
            hierarchical=hierarchical,
        )
        self._steps = [IngestStageChunkStepChunk(chunker)]

    @property
    def children(self) -> list:
        """The single structure-aware chunk step."""
        return self._steps

    def aggregate(self, child_outputs: dict[str, NodeOutput]) -> IngestStageChunkOutput:
        """
        Combine the single step's output into the stage output.

        Args:
            child_outputs (dict[str, NodeOutput]): Step key -> its output.

        Returns:
            IngestStageChunkOutput: The assembled chunk result.
        """
        # 1. Pull the chunk step's typed output by its step key.
        chunked = child_outputs["chunk"]

        # 2. Surface the chunk list and the full chunk result downstream.
        return IngestStageChunkOutput(
            chunks=chunked.chunks,
            chunk_result=chunked.chunk_result,
        )


__all__ = ["IngestStageChunk"]

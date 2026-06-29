# ====== Code Summary ======
# IngestStageChunk — the chunk stage of the ingest pipeline (StageKey.CHUNK). It owns a single step
# (structure-aware chunking) built around a constructor-injected chunking engine whose heading rules,
# atomic policy, and flat/hierarchical mode come from the co-located ``Config`` while the splitter
# instance is injected as a SERVICE (the assembler builds it from ``Config.split_method``).
# IDEMPOTENT_WRITE: chunk ids are deterministic (UUID5 of doc_id + block_ids + config_hash + ordinal)
# and the Postgres upsert is idempotent, so the stage is never node-cached.

# ====== Internal Project Imports ======
from common_libs.pipelines import CachePolicy, NodeOutput, StageKey, StageSpec

# ====== Local Project Imports ======
from ..base import IngestStageBase
from .config import IngestStageChunkConfig
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
    Config = IngestStageChunkConfig

    def __init__(
        self,
        config: IngestStageChunkConfig | None = None,
        *,
        splitter: SectionSplitter | None = None,
    ) -> None:
        """
        Build the chunking engine from the co-located config + injected splitter and wire the step.

        Args:
            config (IngestStageChunkConfig | None): The structure-aware chunking knobs (heading rules,
                merge/breadcrumb flags, atomic policy, flat/hierarchical mode, split-method choice).
                When None, the default config is used.
            splitter (SectionSplitter | None): The built intra-section splitter SERVICE — the assembler
                instantiates it from ``config.split_method`` and injects it here. None -> the chunking
                engine falls back to a default TokenBudgetSplitter.
        """
        super().__init__()
        self._config = config if config is not None else IngestStageChunkConfig()
        chunker = StructureAwareChunker(
            splitter=splitter,
            heading_rules=self._config.heading_rules,
            reinject_breadcrumb=self._config.reinject_breadcrumb,
            merge_short_sections=self._config.merge_short_sections,
            atomic=self._config.atomic,
            cross_references=self._config.cross_references,
            hierarchical=self._config.hierarchical,
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

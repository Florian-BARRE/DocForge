# ====== Code Summary ======
# IngestStageEmbedIndex — the last stage of the ingest pipeline (StageKey.EMBED_INDEX). It assembles
# its six steps (plan_vectors -> embed_content / embed_fields -> assemble_points -> upsert_qdrant ->
# persist_chunks; the engine derives that order from their input bindings) and surfaces the single
# embed result. IDEMPOTENT_WRITE: idempotency comes from the Qdrant + Postgres upserts, not the node
# cache. The collection_id activation gate is enforced UPSTREAM by the engine's should_run hook.

# ====== Internal Project Imports ======
from common_libs.pipelines import CachePolicy, NodeOutput, StageKey, StageSpec

# ====== Local Project Imports ======
from ..base import IngestStageBase
from .context import IngestStageEmbedIndexContext
from .errors import IngestStageEmbedIndexError
from .io import IngestStageEmbedIndexInput, IngestStageEmbedIndexOutput
from .steps import (
    IngestStageEmbedIndexStepAssemblePoints,
    IngestStageEmbedIndexStepEmbedContent,
    IngestStageEmbedIndexStepEmbedFields,
    IngestStageEmbedIndexStepPersistChunks,
    IngestStageEmbedIndexStepPlanVectors,
    IngestStageEmbedIndexStepUpsertQdrant,
)

# Default texts sent per embed chain attempt (matches the legacy S6 batch size).
_DEFAULT_EMBED_BATCH_SIZE = 64


class IngestStageEmbedIndex(IngestStageBase):
    """
    Embed & index stage — embed chunk bodies + metadata fields, upsert to Qdrant, persist to Postgres.

    Declares its six steps; the engine orders + runs them and the stage surfaces the embed result.
    The embed chain / Qdrant client / Postgres client are injected services (declared by the steps);
    the only construction-time config is the embed batch size.
    """

    SPEC = StageSpec(
        key=StageKey.EMBED_INDEX,
        name="Embed & Index",
        description=(
            "Embed chunk bodies + metadata-field values, upsert multi-vector points to Qdrant, and "
            "persist chunks to Postgres."
        ),
        cache_policy=CachePolicy.IDEMPOTENT_WRITE,
    )
    Input = IngestStageEmbedIndexInput
    Output = IngestStageEmbedIndexOutput
    Context = IngestStageEmbedIndexContext
    Error = IngestStageEmbedIndexError

    def __init__(self, embed_batch_size: int = _DEFAULT_EMBED_BATCH_SIZE) -> None:
        """
        Build the six embed_index steps in declaration order (the engine topo-orders them).

        Args:
            embed_batch_size (int): Texts sent per embed chain attempt (shared by both embed steps).
        """
        super().__init__()
        self._steps = [
            IngestStageEmbedIndexStepPlanVectors(),
            IngestStageEmbedIndexStepEmbedContent(embed_batch_size),
            IngestStageEmbedIndexStepEmbedFields(embed_batch_size),
            IngestStageEmbedIndexStepAssemblePoints(),
            IngestStageEmbedIndexStepUpsertQdrant(),
            IngestStageEmbedIndexStepPersistChunks(),
        ]

    @property
    def children(self) -> list:
        """The embed_index steps (the engine orders them by their input bindings)."""
        return self._steps

    def aggregate(self, child_outputs: dict[str, NodeOutput]) -> IngestStageEmbedIndexOutput:
        """
        Combine the step outputs into the stage output (the persist step holds the final result).

        Args:
            child_outputs (dict[str, NodeOutput]): Step key -> its output.

        Returns:
            IngestStageEmbedIndexOutput: The assembled embed + index result.
        """
        # 1. The persist_chunks step produces the assembled embed result (counts + traces).
        persisted = child_outputs["persist_chunks"]

        # 2. Surface it as the single downstream-facing artefact.
        return IngestStageEmbedIndexOutput(embed_result=persisted.embed_result)


__all__ = ["IngestStageEmbedIndex"]

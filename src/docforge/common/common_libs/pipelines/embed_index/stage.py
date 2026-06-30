# ====== Code Summary ======
# The embed_index stage — a GROUP wiring its six action nodes (plan_vectors -> embed_content ->
# embed_fields -> assemble_points -> upsert_qdrant -> persist_chunks) with ``always`` transitions (a
# sequence). It consumes the contextualised/metagen'd chunks + merged doc_meta from the metagen
# sibling, plus the activation collection id and the collection's metadata field defs from the run
# input. Its typed Output surfaces the single embed result (counts + per-batch embed chain traces).
# Idempotency comes from the Qdrant + Postgres upserts — the worker gates the whole stage when there
# is no target collection (collection_id None), so the bindings stay required=False.

# ====== Standard Library Imports ======
from typing import Annotated, Any

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.pipelines.flow import (
    FromNode,
    FromRunInput,
    GroupNode,
    NodeInput,
    NodeOutput,
    Transition,
)

# ====== Local Project Imports ======
from .nodes import (
    EmbedIndexAssemblePoints,
    EmbedIndexEmbedContent,
    EmbedIndexEmbedFields,
    EmbedIndexPersistChunks,
    EmbedIndexPlanVectors,
    EmbedIndexUpsertQdrant,
)
from .result import EmbedIndexResult

# Default number of texts sent to the embed backend per request (shared by both embed nodes).
_DEFAULT_EMBED_BATCH_SIZE = 64


class EmbedIndexStageInput(NodeInput):
    """
    The embed_index stage input.

    Attributes:
        chunks (list[Chunk]): Contextualised chunks (embed_text + derived_meta) from the metagen stage.
        doc_meta (dict): Merged document-level metadata (implicit < generated < user) from metagen.
        collection_id (str | None): Target collection — the stage runs only when a collection is set;
            None resolves cleanly so the worker's gate can skip the whole stage (chunks are then
            persisted to Postgres only).
        metadata_fields (list | None): Collection metadata field defs (drive the vector plan + payload).
    """

    chunks: Annotated[list[Chunk], FromNode("metagen", "chunks")]
    doc_meta: Annotated[dict[str, Any], FromNode("metagen", "doc_meta")]
    collection_id: Annotated[str | None, FromRunInput(required=False)]
    metadata_fields: Annotated[list[Any] | None, FromRunInput(required=False)]


class EmbedIndexStageOutput(NodeOutput):
    """
    The embed_index stage output — the assembled embed + index result.

    Attributes:
        embed_result (EmbedIndexResult): Counts (embedded / upserted / persisted), target collection,
            per-field vector count, and the per-batch embed chain traces.
    """

    embed_result: EmbedIndexResult


class EmbedIndexStage(GroupNode):
    """Embed & index: plan vectors -> embed content/fields -> assemble -> upsert Qdrant -> persist."""

    Input = EmbedIndexStageInput
    Output = EmbedIndexStageOutput

    def __init__(self, embed_batch_size: int = _DEFAULT_EMBED_BATCH_SIZE) -> None:
        """
        Wire the six embed_index nodes as a sequence (``always`` edges).

        Args:
            embed_batch_size (int): Texts sent per embed-chain attempt, shared by both embed nodes.
        """
        super().__init__(
            "embed_index",
            [
                EmbedIndexPlanVectors("plan_vectors"),
                EmbedIndexEmbedContent("embed_content", embed_batch_size),
                EmbedIndexEmbedFields("embed_fields", embed_batch_size),
                EmbedIndexAssemblePoints("assemble_points"),
                EmbedIndexUpsertQdrant("upsert_qdrant"),
                EmbedIndexPersistChunks("persist_chunks"),
            ],
            [
                Transition("plan_vectors", "embed_content"),
                Transition("embed_content", "embed_fields"),
                Transition("embed_fields", "assemble_points"),
                Transition("assemble_points", "upsert_qdrant"),
                Transition("upsert_qdrant", "persist_chunks"),
            ],
        )

    def assemble(self, outputs: dict, terminal: NodeOutput) -> EmbedIndexStageOutput:
        """
        Surface the embed result the terminal persist node assembled as the stage output.

        Args:
            outputs (dict): The six child outputs by id.
            terminal (NodeOutput): The terminal (persist_chunks) output carrying the embed result.

        Returns:
            EmbedIndexStageOutput: The assembled embed + index result.
        """
        # 1. The persist_chunks node holds the assembled embed result (counts + traces).
        return EmbedIndexStageOutput(embed_result=outputs["persist_chunks"].embed_result)


__all__ = ["EmbedIndexStage", "EmbedIndexStageInput", "EmbedIndexStageOutput"]

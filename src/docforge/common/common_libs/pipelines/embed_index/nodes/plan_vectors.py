# ====== Code Summary ======
# The plan_vectors node — the first action of the embed_index stage. It derives the vector plan from
# the collection metadata schema (which named dense vectors the semantic fields need and which sparse
# vectors the lexical fields need) and computes the index_chunks: every chunk except hierarchical
# parents (referenced by a child's parent_id), which carry section context but are not indexed in
# Qdrant. Pure (no service); the downstream nodes consume its plan + index_chunks.

# ====== Standard Library Imports ======
from typing import Annotated, Any

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.pipelines.flow import (
    ActionNode,
    Context,
    FromGroupInput,
    NodeInput,
    NodeOutput,
)
from common_libs.search.field_index import FieldIndexHelpers, VectorPlan


class EmbedIndexPlanVectorsInput(NodeInput):
    """
    Input of the plan_vectors node (read from the enclosing stage input).

    Attributes:
        chunks (list[Chunk]): All chunks to index/persist.
        metadata_fields (list | None): Collection metadata field defs that drive the vector plan.
    """

    chunks: Annotated[list[Chunk], FromGroupInput()]
    metadata_fields: Annotated[list[Any] | None, FromGroupInput()]


class EmbedIndexPlanVectorsOutput(NodeOutput):
    """
    Output of the plan_vectors node.

    Attributes:
        plan (VectorPlan): The named dense/sparse vectors the collection schema requires.
        index_chunks (list[Chunk]): Chunks actually indexed in Qdrant (hierarchical parents excluded).
    """

    plan: VectorPlan
    index_chunks: list[Chunk]


class EmbedIndexPlanVectors(ActionNode):
    """
    Derive the vector plan + the indexable chunk set.

    Reads ``chunks`` / ``metadata_fields`` from the stage input; writes the ``plan`` and the
    ``index_chunks`` (hierarchical parents excluded) for the embed + assemble nodes.
    """

    Input = EmbedIndexPlanVectorsInput
    Output = EmbedIndexPlanVectorsOutput

    async def execute(self, ctx: Context) -> EmbedIndexPlanVectorsOutput:
        """
        Derive the vector plan and the indexable chunk set.

        Args:
            ctx (Context): Carries the resolved input (chunks + metadata fields).

        Returns:
            EmbedIndexPlanVectorsOutput: The vector plan + the index_chunks.
        """
        # 1. Derive which named vectors the collection metadata schema requires.
        plan: VectorPlan = FieldIndexHelpers.derive_vector_plan(ctx.input.metadata_fields or [])

        # 2. Hierarchical mode: parents (referenced by a child's parent_id) carry the full section
        #    text but are NOT indexed in Qdrant — only their children are searched. Every chunk
        #    (parents included) is still persisted to Postgres downstream for hydration.
        chunks = ctx.input.chunks
        parent_ids = {c.parent_id for c in chunks if c.parent_id}
        index_chunks = [c for c in chunks if c.id not in parent_ids]
        self.logger.info(
            f"Plan vectors: chunks={len(chunks)} index_chunks={len(index_chunks)} "
            f"dense_fields={len(plan.dense)} sparse_fields={len(plan.sparse)}"
        )

        # 3. Return the plan + the indexable chunk set for the embed + assemble nodes.
        return EmbedIndexPlanVectorsOutput(plan=plan, index_chunks=index_chunks)


__all__ = ["EmbedIndexPlanVectors", "EmbedIndexPlanVectorsInput", "EmbedIndexPlanVectorsOutput"]

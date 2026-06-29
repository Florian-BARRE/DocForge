# ====== Code Summary ======
# IngestStageEmbedIndexStepPlanVectors — the first embed_index step. It derives the vector plan from
# the collection metadata schema (which named dense vectors the semantic fields need and which sparse
# vectors the lexical fields need) and computes the index_chunks: every chunk except hierarchical
# parents (referenced by a child's parent_id), which carry section context but are not indexed in
# Qdrant. Pure (no service); the downstream steps consume its plan + index_chunks.

# ====== Internal Project Imports ======
from common_libs.pipelines import NodeSpec
from common_libs.search.field_index import FieldIndexHelpers

# ====== Local Project Imports ======
from ..base import IngestStageEmbedIndexStepBase
from .context import IngestStageEmbedIndexStepPlanVectorsContext
from .errors import IngestStageEmbedIndexStepPlanVectorsError
from .io import (
    IngestStageEmbedIndexStepPlanVectorsInput,
    IngestStageEmbedIndexStepPlanVectorsOutput,
)


class IngestStageEmbedIndexStepPlanVectors(IngestStageEmbedIndexStepBase):
    """
    Derive the vector plan + the indexable chunk set.

    Reads ``chunks`` / ``metadata_fields`` from the parent stage input; writes the ``plan`` and the
    ``index_chunks`` (hierarchical parents excluded) for the embed + assemble steps.
    """

    SPEC = NodeSpec(
        key="plan_vectors",
        name="Plan vectors",
        description="Derive named dense/sparse vectors from the schema + drop hierarchical parents.",
    )
    Input = IngestStageEmbedIndexStepPlanVectorsInput
    Output = IngestStageEmbedIndexStepPlanVectorsOutput
    Context = IngestStageEmbedIndexStepPlanVectorsContext
    Error = IngestStageEmbedIndexStepPlanVectorsError

    async def execute(
        self, ctx: IngestStageEmbedIndexStepPlanVectorsContext
    ) -> IngestStageEmbedIndexStepPlanVectorsOutput:
        """
        Derive the vector plan and the indexable chunk set.

        Args:
            ctx (IngestStageEmbedIndexStepPlanVectorsContext): Typed input (chunks + metadata fields).

        Returns:
            IngestStageEmbedIndexStepPlanVectorsOutput: The vector plan + the index_chunks.

        Raises:
            IngestStageEmbedIndexStepPlanVectorsError: When the vector plan cannot be derived.
        """
        # 1. Derive which named vectors the collection metadata schema requires.
        try:
            plan = FieldIndexHelpers.derive_vector_plan(ctx.input.metadata_fields or [])
        except Exception as exc:
            self.logger.error(f"Vector plan derivation failed: {exc}")
            raise IngestStageEmbedIndexStepPlanVectorsError(
                "Failed to derive the vector plan from the metadata schema.",
                node_key=self.key,
                cause=exc,
            ) from exc

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

        # 3. Return the plan + the indexable chunk set for the embed + assemble steps.
        return IngestStageEmbedIndexStepPlanVectorsOutput(plan=plan, index_chunks=index_chunks)


__all__ = ["IngestStageEmbedIndexStepPlanVectors"]

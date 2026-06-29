# ====== Code Summary ======
# IngestStageEmbedIndexStepAssemblePoints — the point-assembly step. It builds the named dense/sparse
# vector maps Qdrant upsert consumes (content body + one per planned field) and the per-chunk lean
# filterable payloads (base provenance + filterable field values). Pure (no service); delegates the
# mappings to IngestStageEmbedIndexIndexHelpers. Its output is the full Qdrant upsert payload.

# ====== Internal Project Imports ======
from common_libs.pipelines import NodeSpec

# ====== Local Project Imports ======
from ...helpers_index import IngestStageEmbedIndexIndexHelpers
from ..base import IngestStageEmbedIndexStepBase
from .context import IngestStageEmbedIndexStepAssemblePointsContext
from .errors import IngestStageEmbedIndexStepAssemblePointsError
from .io import (
    IngestStageEmbedIndexStepAssemblePointsInput,
    IngestStageEmbedIndexStepAssemblePointsOutput,
)


class IngestStageEmbedIndexStepAssemblePoints(IngestStageEmbedIndexStepBase):
    """
    Assemble the Qdrant named-vector maps + per-chunk filterable payloads.

    Reads the plan + content/field vectors + metadata; writes the chunk ids, the named dense/sparse
    vector maps, and the per-chunk payloads for the Qdrant upsert.
    """

    SPEC = NodeSpec(
        key="assemble_points",
        name="Assemble points",
        description="Build the named-vector maps + filterable payloads for the Qdrant upsert.",
    )
    Input = IngestStageEmbedIndexStepAssemblePointsInput
    Output = IngestStageEmbedIndexStepAssemblePointsOutput
    Context = IngestStageEmbedIndexStepAssemblePointsContext
    Error = IngestStageEmbedIndexStepAssemblePointsError

    async def execute(
        self, ctx: IngestStageEmbedIndexStepAssemblePointsContext
    ) -> IngestStageEmbedIndexStepAssemblePointsOutput:
        """
        Assemble the named-vector maps + the per-chunk Qdrant payloads.

        Args:
            ctx (IngestStageEmbedIndexStepAssemblePointsContext): Typed input (plan + vectors + meta).

        Returns:
            IngestStageEmbedIndexStepAssemblePointsOutput: chunk ids + vector maps + payloads.

        Raises:
            IngestStageEmbedIndexStepAssemblePointsError: When the maps/payloads cannot be assembled.
        """
        data = ctx.input
        try:
            # 1. Assemble the named dense/sparse vector maps (content body + one per planned field).
            dense_by_vector, sparse_by_vector = IngestStageEmbedIndexIndexHelpers.build_vector_maps(
                data.plan,
                data.content_dense,
                data.content_sparse,
                data.field_dense,
                data.field_sparse,
            )

            # 2. Build the per-chunk lean filterable payloads + the matching point ids.
            metadata_fields = data.metadata_fields or []
            doc_meta = data.doc_meta or {}
            payloads = [
                IngestStageEmbedIndexIndexHelpers.build_payload(c, metadata_fields, doc_meta)
                for c in data.index_chunks
            ]
            chunk_ids = [c.id for c in data.index_chunks]
        except Exception as exc:
            self.logger.error(f"Point assembly failed: {exc}")
            raise IngestStageEmbedIndexStepAssemblePointsError(
                "Failed to assemble the Qdrant vector maps or payloads.",
                node_key=self.key,
                cause=exc,
            ) from exc

        self.logger.info(
            f"Assemble points: points={len(chunk_ids)} dense_vectors={len(dense_by_vector)} "
            f"sparse_vectors={len(sparse_by_vector)}"
        )

        # 3. Hand the full Qdrant upsert payload to the upsert step.
        return IngestStageEmbedIndexStepAssemblePointsOutput(
            chunk_ids=chunk_ids,
            dense_by_vector=dense_by_vector,
            sparse_by_vector=sparse_by_vector,
            payloads=payloads,
        )


__all__ = ["IngestStageEmbedIndexStepAssemblePoints"]

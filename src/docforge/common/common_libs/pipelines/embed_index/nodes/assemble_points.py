# ====== Code Summary ======
# The assemble_points node — the point-assembly action. It builds the named dense/sparse vector maps
# Qdrant upsert consumes (content body + one per planned field) and the per-chunk lean filterable
# payloads (base provenance + filterable field values). Pure (no service); delegates the mappings to
# EmbedIndexIndexHelpers. Its output is the full Qdrant upsert payload.

# ====== Standard Library Imports ======
from typing import Annotated, Any

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.pipelines.flow import (
    ActionNode,
    Context,
    FromGroupInput,
    FromNode,
    NodeInput,
    NodeOutput,
)
from common_libs.search.field_index import VectorPlan

# ====== Local Project Imports ======
from ..helpers_index import EmbedIndexIndexHelpers


class EmbedIndexAssemblePointsInput(NodeInput):
    """
    Input of the assemble_points node.

    Attributes:
        index_chunks (list[Chunk]): Indexable chunks (from plan_vectors).
        plan (VectorPlan): The named dense/sparse vector plan (from plan_vectors).
        content_dense (list): Per-chunk content dense vectors (from embed_content).
        content_sparse (list | None): Per-chunk content sparse vectors (from embed_content), or None.
        field_dense (dict): Field name -> per-chunk dense vectors (from embed_fields).
        field_sparse (dict): Field name -> per-chunk sparse vectors (from embed_fields).
        metadata_fields (list | None): Collection metadata field defs (filterable payload assembly).
        doc_meta (dict | None): Document-level field values (filterable payload assembly).
    """

    index_chunks: Annotated[list[Chunk], FromNode("plan_vectors", "index_chunks")]
    plan: Annotated[VectorPlan, FromNode("plan_vectors", "plan")]
    content_dense: Annotated[list[list[float] | None], FromNode("embed_content", "content_dense")]
    content_sparse: Annotated[
        list[dict[int, float] | None] | None, FromNode("embed_content", "content_sparse")
    ]
    field_dense: Annotated[
        dict[str, list[list[float] | None]], FromNode("embed_fields", "field_dense")
    ]
    field_sparse: Annotated[
        dict[str, list[dict[int, float] | None]], FromNode("embed_fields", "field_sparse")
    ]
    metadata_fields: Annotated[list[Any] | None, FromGroupInput()]
    doc_meta: Annotated[dict[str, Any] | None, FromGroupInput()]


class EmbedIndexAssemblePointsOutput(NodeOutput):
    """
    Output of the assemble_points node.

    Attributes:
        chunk_ids (list[str]): Point ids for the Qdrant upsert (one per index chunk).
        dense_by_vector (dict): Named-vector key -> per-chunk dense vectors.
        sparse_by_vector (dict): Named-vector key -> per-chunk sparse vectors.
        payloads (list[dict]): Per-chunk filterable Qdrant payloads.
    """

    chunk_ids: list[str]
    dense_by_vector: dict[str, list[list[float] | None]]
    sparse_by_vector: dict[str, list[dict[int, float] | None]]
    payloads: list[dict[str, Any]]


class EmbedIndexAssemblePoints(ActionNode):
    """
    Assemble the Qdrant named-vector maps + per-chunk filterable payloads.

    Reads the plan + content/field vectors + metadata; writes the chunk ids, the named dense/sparse
    vector maps, and the per-chunk payloads for the Qdrant upsert.
    """

    Input = EmbedIndexAssemblePointsInput
    Output = EmbedIndexAssemblePointsOutput

    async def execute(self, ctx: Context) -> EmbedIndexAssemblePointsOutput:
        """
        Assemble the named-vector maps + the per-chunk Qdrant payloads.

        Args:
            ctx (Context): The resolved input (plan + vectors + metadata).

        Returns:
            EmbedIndexAssemblePointsOutput: chunk ids + vector maps + payloads.
        """
        data = ctx.input

        # 1. Assemble the named dense/sparse vector maps (content body + one per planned field).
        dense_by_vector, sparse_by_vector = EmbedIndexIndexHelpers.build_vector_maps(
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
            EmbedIndexIndexHelpers.build_payload(c, metadata_fields, doc_meta)
            for c in data.index_chunks
        ]
        chunk_ids = [c.id for c in data.index_chunks]
        self.logger.info(
            f"Assemble points: points={len(chunk_ids)} dense_vectors={len(dense_by_vector)} "
            f"sparse_vectors={len(sparse_by_vector)}"
        )

        # 3. Hand the full Qdrant upsert payload to the upsert node.
        return EmbedIndexAssemblePointsOutput(
            chunk_ids=chunk_ids,
            dense_by_vector=dense_by_vector,
            sparse_by_vector=sparse_by_vector,
            payloads=payloads,
        )


__all__ = [
    "EmbedIndexAssemblePoints",
    "EmbedIndexAssemblePointsInput",
    "EmbedIndexAssemblePointsOutput",
]

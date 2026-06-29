# ====== Code Summary ======
# IO contract for the assemble_points step: it consumes the plan + index_chunks (plan_vectors), the
# content vectors (embed_content), the per-field vectors (embed_fields), and the metadata fields +
# doc_meta (parent stage input), and produces the Qdrant upsert payload: chunk ids, the named
# dense/sparse vector maps, and the per-chunk filterable payloads.

# ====== Standard Library Imports ======
from typing import Annotated, Any

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.pipelines import FromParent, FromSibling, NodeInput, NodeOutput
from common_libs.search.field_index import VectorPlan


class IngestStageEmbedIndexStepAssemblePointsInput(NodeInput):
    """
    Input of the assemble_points step.

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

    index_chunks: Annotated[
        list[Chunk], FromSibling(producer="plan_vectors", field="index_chunks")
    ]
    plan: Annotated[VectorPlan, FromSibling(producer="plan_vectors", field="plan")]
    content_dense: Annotated[
        list[list[float] | None], FromSibling(producer="embed_content", field="content_dense")
    ]
    content_sparse: Annotated[
        list[dict[int, float] | None] | None,
        FromSibling(producer="embed_content", field="content_sparse", required=False),
    ]
    field_dense: Annotated[
        dict[str, list[list[float] | None]],
        FromSibling(producer="embed_fields", field="field_dense"),
    ]
    field_sparse: Annotated[
        dict[str, list[dict[int, float] | None]],
        FromSibling(producer="embed_fields", field="field_sparse"),
    ]
    metadata_fields: Annotated[list[Any] | None, FromParent(required=False)]
    doc_meta: Annotated[dict[str, Any] | None, FromParent(required=False)]


class IngestStageEmbedIndexStepAssemblePointsOutput(NodeOutput):
    """
    Output of the assemble_points step.

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


__all__ = [
    "IngestStageEmbedIndexStepAssemblePointsInput",
    "IngestStageEmbedIndexStepAssemblePointsOutput",
]

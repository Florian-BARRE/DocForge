# ====== Code Summary ======
# IO contract for the upsert_qdrant step: it consumes the collection id + the chunks (parent stage
# input, for the no-op guard), the plan + dimension (for the collection schema), and the assembled
# chunk ids / vector maps / payloads (assemble_points), and produces the upsert count + collection name.

# ====== Standard Library Imports ======
from typing import Annotated, Any

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.pipelines import FromParent, FromSibling, NodeInput, NodeOutput
from common_libs.search.field_index import VectorPlan


class IngestStageEmbedIndexStepUpsertQdrantInput(NodeInput):
    """
    Input of the upsert_qdrant step.

    Attributes:
        collection_id (str): Target Qdrant collection (from the parent stage input).
        chunks (list[Chunk]): All chunks (from the parent stage input) — drives the no-op guard:
            an empty chunk set skips ensure_collection + upsert entirely (legacy parity).
        plan (VectorPlan): The named dense/sparse vector plan (from plan_vectors) — collection schema.
        dimension (int): Dense vector dimension (from embed_content) — collection schema.
        chunk_ids (list[str]): Point ids to upsert (from assemble_points).
        dense_by_vector (dict): Named-vector key -> per-chunk dense vectors (from assemble_points).
        sparse_by_vector (dict): Named-vector key -> per-chunk sparse vectors (from assemble_points).
        payloads (list[dict]): Per-chunk filterable payloads (from assemble_points).
    """

    collection_id: Annotated[str, FromParent()]
    chunks: Annotated[list[Chunk], FromParent()]
    plan: Annotated[VectorPlan, FromSibling(producer="plan_vectors", field="plan")]
    dimension: Annotated[int, FromSibling(producer="embed_content", field="dimension")]
    chunk_ids: Annotated[list[str], FromSibling(producer="assemble_points", field="chunk_ids")]
    dense_by_vector: Annotated[
        dict[str, list[list[float] | None]],
        FromSibling(producer="assemble_points", field="dense_by_vector"),
    ]
    sparse_by_vector: Annotated[
        dict[str, list[dict[int, float] | None]],
        FromSibling(producer="assemble_points", field="sparse_by_vector"),
    ]
    payloads: Annotated[
        list[dict[str, Any]], FromSibling(producer="assemble_points", field="payloads")
    ]


class IngestStageEmbedIndexStepUpsertQdrantOutput(NodeOutput):
    """
    Output of the upsert_qdrant step.

    Attributes:
        n_upserted (int): Number of points upserted to Qdrant (0 when there were no chunks).
        collection_name (str): The Qdrant collection the points were upserted into.
    """

    n_upserted: int
    collection_name: str


__all__ = [
    "IngestStageEmbedIndexStepUpsertQdrantInput",
    "IngestStageEmbedIndexStepUpsertQdrantOutput",
]

# ====== Code Summary ======
# IO contract for the persist_chunks step: it consumes all chunks + the collection id (parent stage
# input), the index_chunks + plan (plan_vectors), the upsert count (upsert_qdrant), and the per-batch
# embed traces (embed_content + embed_fields), and produces the assembled embed_index result (counts +
# target collection + per-field vector count + chain traces).

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.domain.ir.models import ChainTrace
from common_libs.pipelines import FromParent, FromSibling, NodeInput, NodeOutput
from common_libs.search.field_index import VectorPlan

# ====== Local Project Imports ======
from ...result import IngestStageEmbedIndexResult


class IngestStageEmbedIndexStepPersistChunksInput(NodeInput):
    """
    Input of the persist_chunks step.

    Attributes:
        chunks (list[Chunk]): All chunks (parents included) to persist to Postgres.
        collection_id (str): Target collection (carried into the result).
        index_chunks (list[Chunk]): Indexed chunks (from plan_vectors) — drives the embedded count.
        plan (VectorPlan): The vector plan (from plan_vectors) — drives the field-vector count.
        n_upserted (int): Points upserted to Qdrant (from upsert_qdrant) — orders persist after upsert.
        content_traces (list[ChainTrace]): Content embed batch traces (from embed_content).
        field_traces (list[ChainTrace]): Field embed batch traces (from embed_fields).
    """

    chunks: Annotated[list[Chunk], FromParent()]
    collection_id: Annotated[str, FromParent()]
    index_chunks: Annotated[
        list[Chunk], FromSibling(producer="plan_vectors", field="index_chunks")
    ]
    plan: Annotated[VectorPlan, FromSibling(producer="plan_vectors", field="plan")]
    n_upserted: Annotated[int, FromSibling(producer="upsert_qdrant", field="n_upserted")]
    content_traces: Annotated[
        list[ChainTrace], FromSibling(producer="embed_content", field="content_traces")
    ]
    field_traces: Annotated[
        list[ChainTrace], FromSibling(producer="embed_fields", field="field_traces")
    ]


class IngestStageEmbedIndexStepPersistChunksOutput(NodeOutput):
    """
    Output of the persist_chunks step.

    Attributes:
        embed_result (IngestStageEmbedIndexResult): The assembled embed + index result (counts +
            target collection + per-field vector count + per-batch embed chain traces).
    """

    embed_result: IngestStageEmbedIndexResult


__all__ = [
    "IngestStageEmbedIndexStepPersistChunksInput",
    "IngestStageEmbedIndexStepPersistChunksOutput",
]

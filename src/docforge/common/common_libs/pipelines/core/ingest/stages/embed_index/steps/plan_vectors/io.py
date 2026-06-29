# ====== Code Summary ======
# IO contract for the plan_vectors step: it reads the chunks + collection metadata field defs from
# the parent stage input and produces the vector plan (which named dense/sparse vectors the schema
# needs) plus the index_chunks (parents excluded — hierarchical parents are persisted but not indexed).

# ====== Standard Library Imports ======
from typing import Annotated, Any

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.pipelines import FromParent, NodeInput, NodeOutput
from common_libs.search.field_index import VectorPlan


class IngestStageEmbedIndexStepPlanVectorsInput(NodeInput):
    """
    Input of the plan_vectors step (read from the parent stage input).

    Attributes:
        chunks (list[Chunk]): All chunks to index/persist.
        metadata_fields (list | None): Collection metadata field defs that drive the vector plan.
    """

    chunks: Annotated[list[Chunk], FromParent()]
    metadata_fields: Annotated[list[Any] | None, FromParent(required=False)]


class IngestStageEmbedIndexStepPlanVectorsOutput(NodeOutput):
    """
    Output of the plan_vectors step.

    Attributes:
        plan (VectorPlan): The named dense/sparse vectors the collection schema requires.
        index_chunks (list[Chunk]): Chunks actually indexed in Qdrant (hierarchical parents excluded).
    """

    plan: VectorPlan
    index_chunks: list[Chunk]


__all__ = [
    "IngestStageEmbedIndexStepPlanVectorsInput",
    "IngestStageEmbedIndexStepPlanVectorsOutput",
]

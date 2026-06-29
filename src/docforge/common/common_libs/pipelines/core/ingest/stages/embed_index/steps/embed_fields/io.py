# ====== Code Summary ======
# IO contract for the embed_fields step: it consumes the vector plan + index_chunks from the
# plan_vectors sibling and the doc_meta from the parent stage input, and produces the per-field
# dense/sparse vectors (keyed by field name, each aligned 1:1 with index_chunks) + the chain traces.

# ====== Standard Library Imports ======
from typing import Annotated, Any

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.domain.ir.models import ChainTrace
from common_libs.pipelines import FromParent, FromSibling, NodeInput, NodeOutput
from common_libs.search.field_index import VectorPlan


class IngestStageEmbedIndexStepEmbedFieldsInput(NodeInput):
    """
    Input of the embed_fields step.

    Attributes:
        plan (VectorPlan): The named dense/sparse vectors the schema requires (from plan_vectors).
        index_chunks (list[Chunk]): Indexable chunks (from plan_vectors) whose field values are embedded.
        doc_meta (dict | None): Document-level field values (from the parent stage input).
    """

    plan: Annotated[VectorPlan, FromSibling(producer="plan_vectors", field="plan")]
    index_chunks: Annotated[
        list[Chunk], FromSibling(producer="plan_vectors", field="index_chunks")
    ]
    doc_meta: Annotated[dict[str, Any] | None, FromParent(required=False)]


class IngestStageEmbedIndexStepEmbedFieldsOutput(NodeOutput):
    """
    Output of the embed_fields step.

    Attributes:
        field_dense (dict): Field name -> per-chunk dense vectors (None where the chunk has no value).
        field_sparse (dict): Field name -> per-chunk sparse vectors (None where the chunk has no value).
        field_traces (list[ChainTrace]): One embed chain trace per batch actually embedded.
    """

    field_dense: dict[str, list[list[float] | None]]
    field_sparse: dict[str, list[dict[int, float] | None]]
    field_traces: list[ChainTrace]


__all__ = [
    "IngestStageEmbedIndexStepEmbedFieldsInput",
    "IngestStageEmbedIndexStepEmbedFieldsOutput",
]

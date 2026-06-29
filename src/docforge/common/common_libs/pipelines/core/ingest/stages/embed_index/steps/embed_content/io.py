# ====== Code Summary ======
# IO contract for the embed_content step: it consumes the index_chunks from the plan_vectors sibling
# and produces the per-chunk content dense/sparse vectors (positionally aligned 1:1 with the chunks),
# the embed dimension (for the Qdrant collection schema), and the per-batch embed chain traces.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.domain.ir.models import ChainTrace
from common_libs.pipelines import FromSibling, NodeInput, NodeOutput


class IngestStageEmbedIndexStepEmbedContentInput(NodeInput):
    """
    Input of the embed_content step.

    Attributes:
        index_chunks (list[Chunk]): Indexable chunks (from the plan_vectors step) to embed.
    """

    index_chunks: Annotated[
        list[Chunk], FromSibling(producer="plan_vectors", field="index_chunks")
    ]


class IngestStageEmbedIndexStepEmbedContentOutput(NodeOutput):
    """
    Output of the embed_content step.

    Attributes:
        content_dense (list): Per-chunk content dense vectors (aligned 1:1 with index_chunks; None
            where the embed chain degraded for a batch).
        content_sparse (list | None): Per-chunk content sparse vectors, or None when no sparse was
            produced at all.
        dimension (int): Dense vector dimension of the embed chain's first provider (Qdrant schema).
        content_traces (list[ChainTrace]): One embed chain trace per batch.
    """

    content_dense: list[list[float] | None]
    content_sparse: list[dict[int, float] | None] | None = None
    dimension: int
    content_traces: list[ChainTrace]


__all__ = [
    "IngestStageEmbedIndexStepEmbedContentInput",
    "IngestStageEmbedIndexStepEmbedContentOutput",
]

# ====== Code Summary ======
# The embed_content node — the content-embedding action. It runs the embed chain over the indexable
# chunk bodies (``embed_text``) in batches, returning the per-chunk dense/sparse vectors positionally
# aligned 1:1 with the chunks (degraded batches emit None placeholders), the embed dimension (for the
# Qdrant collection schema), and the per-batch chain traces. The embed chain is an injected service;
# the batch size is a construction-time argument.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.domain.ir.models import ChainTrace
from common_libs.pipelines.flow import ActionNode, Context, FromNode, NodeInput, NodeOutput

# ====== Local Project Imports ======
from ..helpers_embed import EmbedIndexEmbedHelpers


class EmbedIndexEmbedContentInput(NodeInput):
    """
    Input of the embed_content node.

    Attributes:
        index_chunks (list[Chunk]): Indexable chunks (from the plan_vectors node) to embed.
    """

    index_chunks: Annotated[list[Chunk], FromNode("plan_vectors", "index_chunks")]


class EmbedIndexEmbedContentOutput(NodeOutput):
    """
    Output of the embed_content node.

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


class EmbedIndexEmbedContent(ActionNode):
    """
    Embed the chunk bodies into dense/sparse content vectors via the embed chain.

    Reads ``index_chunks``; writes the per-chunk content vectors + the embed dimension + the chain
    traces. The vectors are positionally aligned with ``index_chunks`` (load-bearing for the upsert).
    """

    Input = EmbedIndexEmbedContentInput
    Output = EmbedIndexEmbedContentOutput

    def __init__(self, node_id: str, embed_batch_size: int) -> None:
        """
        Wire the node with its embed batch size.

        Args:
            node_id (str): The node's id (unique among its siblings).
            embed_batch_size (int): Texts sent per embed chain attempt.
        """
        super().__init__(node_id)
        self._embed_batch_size = embed_batch_size

    async def execute(self, ctx: Context) -> EmbedIndexEmbedContentOutput:
        """
        Embed the chunk bodies and return their vectors + the embed dimension + the chain traces.

        Args:
            ctx (Context): The resolved input + the injected embed chain service.

        Returns:
            EmbedIndexEmbedContentOutput: Content vectors, dimension, and traces.

        Raises:
            ChainExhaustedError: When the embed chain exhausts under failure_policy="raise".
        """
        # 1. Embed the indexable chunk bodies (batched, positionally aligned 1:1 with the chunks).
        index_chunks = ctx.input.index_chunks
        chain = ctx.service("embed_chain")
        content_dense, content_sparse, traces = await EmbedIndexEmbedHelpers.embed_texts(
            chain,
            [c.embed_text for c in index_chunks],
            self._embed_batch_size,
        )

        # 2. Resolve the dense dimension from the chain's first provider (used to size the collection).
        providers = chain.providers
        dimension = int(getattr(providers[0], "dimension", 0)) if providers else 0
        self.logger.info(
            f"Embed content: chunks={len(index_chunks)} dimension={dimension} batches={len(traces)}"
        )

        # 3. Hand the content vectors + dimension + traces to the assemble / persist nodes.
        return EmbedIndexEmbedContentOutput(
            content_dense=content_dense,
            content_sparse=content_sparse,
            dimension=dimension,
            content_traces=traces,
        )


__all__ = ["EmbedIndexEmbedContent", "EmbedIndexEmbedContentInput", "EmbedIndexEmbedContentOutput"]

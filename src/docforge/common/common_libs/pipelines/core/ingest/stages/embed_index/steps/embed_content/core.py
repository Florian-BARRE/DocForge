# ====== Code Summary ======
# IngestStageEmbedIndexStepEmbedContent — the content-embedding step. It runs the embed chain over
# the indexable chunk bodies (``embed_text``) in batches, returning the per-chunk dense/sparse vectors
# positionally aligned 1:1 with the chunks (degraded batches emit None placeholders), the embed
# dimension (for the Qdrant collection schema), and the per-batch chain traces. Declares the embed
# chain as its only required service; the batch size is a construction-time config.

# ====== Internal Project Imports ======
from common_libs.pipelines import ChainRef, NodeSpec

# ====== Local Project Imports ======
from ...helpers_embed import IngestStageEmbedIndexEmbedHelpers
from ..base import IngestStageEmbedIndexStepBase
from .context import IngestStageEmbedIndexStepEmbedContentContext
from .errors import IngestStageEmbedIndexStepEmbedContentError
from .io import (
    IngestStageEmbedIndexStepEmbedContentInput,
    IngestStageEmbedIndexStepEmbedContentOutput,
)


class IngestStageEmbedIndexStepEmbedContent(IngestStageEmbedIndexStepBase):
    """
    Embed the chunk bodies into dense/sparse content vectors via the embed chain.

    Reads ``index_chunks``; writes the per-chunk content vectors + the embed dimension + the chain
    traces. The vectors are positionally aligned with ``index_chunks`` (load-bearing for the upsert).
    """

    SPEC = NodeSpec(
        key="embed_content",
        name="Embed content",
        description="Embed chunk bodies into dense/sparse content vectors via the embed chain.",
    )
    Input = IngestStageEmbedIndexStepEmbedContentInput
    Output = IngestStageEmbedIndexStepEmbedContentOutput
    Context = IngestStageEmbedIndexStepEmbedContentContext
    Error = IngestStageEmbedIndexStepEmbedContentError
    REQUIRES = (ChainRef(name="embed_chain", category="embed", description="Ordered embed provider chain."),)

    def __init__(self, embed_batch_size: int) -> None:
        """
        Wire the step with its embed batch size.

        Args:
            embed_batch_size (int): Texts sent per embed chain attempt.
        """
        super().__init__()
        self._embed_batch_size = embed_batch_size

    async def execute(
        self, ctx: IngestStageEmbedIndexStepEmbedContentContext
    ) -> IngestStageEmbedIndexStepEmbedContentOutput:
        """
        Embed the chunk bodies and return their vectors + the embed dimension + the chain traces.

        Args:
            ctx (IngestStageEmbedIndexStepEmbedContentContext): Typed input + the embed chain.

        Returns:
            IngestStageEmbedIndexStepEmbedContentOutput: Content vectors, dimension, and traces.

        Raises:
            IngestStageEmbedIndexStepEmbedContentError: When the embed chain exhausts under
                failure_policy="raise" (propagated from the chain).
        """
        # 1. Embed the indexable chunk bodies (batched, positionally aligned 1:1 with the chunks).
        index_chunks = ctx.input.index_chunks
        content_dense, content_sparse, traces = await IngestStageEmbedIndexEmbedHelpers.embed_texts(
            ctx.embed_chain,
            [c.embed_text for c in index_chunks],
            self._embed_batch_size,
        )

        # 2. Resolve the dense dimension from the chain's first provider (used to size the collection).
        providers = ctx.embed_chain.providers
        dimension = int(getattr(providers[0], "dimension", 0)) if providers else 0
        self.logger.info(
            f"Embed content: chunks={len(index_chunks)} dimension={dimension} batches={len(traces)}"
        )

        # 3. Hand the content vectors + dimension + traces to the assemble / persist steps.
        return IngestStageEmbedIndexStepEmbedContentOutput(
            content_dense=content_dense,
            content_sparse=content_sparse,
            dimension=dimension,
            content_traces=traces,
        )


__all__ = ["IngestStageEmbedIndexStepEmbedContent"]

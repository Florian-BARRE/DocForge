# ====== Code Summary ======
# ContextualizeStep — the single native step of the contextualize (S5) stage. This is the
# PURE-LOGIC (non-chain) step case: it has no provider chain at all. It reads the chunk list + the
# current IR from the context, delegates to the existing S5ContextualizeStage (build each chunk's
# embed_text from title + heading breadcrumb + body), and writes the S5Result + the contextualized
# chunks back.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.ingest.stages.base.step import IngestStep

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext
    from common_libs.pipeline.stages.s5_contextualize.core import S5ContextualizeStage


class ContextualizeStep(IngestStep):
    """
    Native contextualize step — pure logic (no provider chain), threading IO via the context.

    Reads ``chunks`` + ``ir``; writes ``s5_result`` and the contextualized ``chunks``.
    """

    KEY: ClassVar[str] = "contextualize"
    NAME: ClassVar[str] = "Contextualize"
    DESCRIPTION: ClassVar[str] = (
        "Build each chunk's embed_text from the document title, heading breadcrumb, and chunk "
        "body."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("chunks", "ir")
    PRODUCES: ClassVar[tuple[str, ...]] = ("s5_result", "chunks")

    def __init__(self, contextualizer: "S5ContextualizeStage") -> None:
        """
        Wire the step around the contextualization implementation.

        Args:
            contextualizer (S5ContextualizeStage): The contextualization implementation.
        """
        IngestStep.__init__(self)
        self._contextualizer = contextualizer

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Run the contextualization implementation and write its output onto the context.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        # 1. Contextualize the chunk list against the current IR.
        result = await self._contextualizer.run(ctx.chunks, ctx.ir)

        # 2. Write the declared PRODUCES back onto the context.
        ctx.s5_result = result
        ctx.chunks = result.chunks


__all__ = ["ContextualizeStep"]

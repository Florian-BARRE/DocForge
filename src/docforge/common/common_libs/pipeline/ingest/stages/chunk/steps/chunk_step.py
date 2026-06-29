# ====== Code Summary ======
# ChunkStep — the single native step of the chunk (S4) stage. It reads the enriched IR from the
# context, delegates to the existing S4ChunkStage (heading-hierarchy-aware, structure-aware
# chunking), and writes the S4Result + the chunk list back.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.ingest.stages.base.step import IngestStep

if TYPE_CHECKING:
    from common_libs.pipeline.stages.context import PipelineContext
    from common_libs.pipeline.stages.s4_chunk.core import S4ChunkStage


class ChunkStep(IngestStep):
    """
    Native chunk step — delegates to the legacy S4 chunking logic, threading IO via the context.

    Reads ``ir``; writes ``chunk_result`` and ``chunks``.
    """

    KEY: ClassVar[str] = "chunk"
    NAME: ClassVar[str] = "Chunk"
    DESCRIPTION: ClassVar[str] = (
        "Split the enriched IR into retrieval chunks using heading-hierarchy-aware, "
        "structure-aware chunking."
    )
    CONSUMES: ClassVar[tuple[str, ...]] = ("ir",)
    PRODUCES: ClassVar[tuple[str, ...]] = ("chunk_result", "chunks")

    def __init__(self, chunker: "S4ChunkStage") -> None:
        """
        Wire the step around the chunking implementation.

        Args:
            chunker (S4ChunkStage): The chunking implementation.
        """
        IngestStep.__init__(self)
        self._chunker = chunker

    async def run(self, ctx: "PipelineContext") -> None:
        """
        Run the chunking implementation and write its output onto the context.

        Args:
            ctx (PipelineContext): The mutable run accumulator.
        """
        # 1. Chunk the current IR.
        result = await self._chunker.run(ctx.ir)

        # 2. Write the declared PRODUCES back onto the context.
        ctx.chunk_result = result
        ctx.chunks = result.chunks


__all__ = ["ChunkStep"]

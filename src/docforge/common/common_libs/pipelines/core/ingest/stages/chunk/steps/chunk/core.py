# ====== Code Summary ======
# IngestStageChunkStepChunk — the single step of the chunk stage. It reads the enriched IR, delegates
# to the structure-aware chunking engine (heading-hierarchy-aware, flat/hierarchical assembly, cross-
# reference linking), and returns the chunk list + the chunk result. The chunking engine is injected
# at construction (its splitter + config are assembly-time choices), so the step requires no service.

# ====== Internal Project Imports ======
from common_libs.pipelines import NodeSpec

# ====== Local Project Imports ======
from ..base import IngestStageChunkStepBase
from .chunker import StructureAwareChunker
from .context import IngestStageChunkStepChunkContext
from .errors import IngestStageChunkStepChunkError
from .io import (
    IngestStageChunkStepChunkInput,
    IngestStageChunkStepChunkOutput,
)


class IngestStageChunkStepChunk(IngestStageChunkStepBase):
    """
    Structure-aware chunking step — split the enriched IR into retrieval chunks.

    Reads ``ir`` from the parent stage input; writes ``chunks`` and ``chunk_result``. The chunking
    engine (splitter + heading rules + atomic policy + flat/hierarchical mode) is constructor-injected
    by the stage, keeping this step a thin, deterministic adapter over the engine.
    """

    SPEC = NodeSpec(
        key="chunk",
        name="Chunk",
        description="Heading-hierarchy-aware, structure-aware splitting of the enriched IR.",
    )
    Input = IngestStageChunkStepChunkInput
    Output = IngestStageChunkStepChunkOutput
    Context = IngestStageChunkStepChunkContext
    Error = IngestStageChunkStepChunkError

    def __init__(self, chunker: StructureAwareChunker) -> None:
        """
        Wire the step around the chunking engine.

        Args:
            chunker (StructureAwareChunker): The configured structure-aware chunking engine.
        """
        super().__init__()
        self._chunker = chunker

    async def execute(
        self, ctx: IngestStageChunkStepChunkContext
    ) -> IngestStageChunkStepChunkOutput:
        """
        Run the chunking engine over the enriched IR and return the chunk artefacts.

        Args:
            ctx (IngestStageChunkStepChunkContext): Typed input carrying the enriched IR.

        Returns:
            IngestStageChunkStepChunkOutput: The chunk list + the chunk result.

        Raises:
            IngestStageChunkStepChunkError: When structure-aware chunking fails.
        """
        # 1. Run the deterministic structure-aware chunker over the enriched IR.
        ir = ctx.input.ir
        try:
            result = await self._chunker.run(ir)
        except Exception as exc:
            self.logger.error(f"Chunking failed for doc_id={ir.doc_id!r}: {exc}")
            raise IngestStageChunkStepChunkError(
                f"Failed to chunk doc_id={ir.doc_id!r}.",
                node_key=self.key,
                cause=exc,
            ) from exc

        # 2. Surface the chunk list and the full chunk result (config_hash + tallies).
        return IngestStageChunkStepChunkOutput(chunks=result.chunks, chunk_result=result)


__all__ = ["IngestStageChunkStepChunk"]

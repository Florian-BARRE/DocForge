# ====== Code Summary ======
# The chunk node — the single elementary action of the chunk stage. It reads the enriched canonical IR
# (from the enclosing stage's input) and delegates to the v1 StructureAwareChunker (heading-hierarchy-
# aware, flat/hierarchical assembly, cross-reference linking) to produce the retrieval chunks plus the
# full chunk result (S4Result, carrying the deterministic config hash). The chunking engine is the reused
# domain algorithm; this node only RESTRUCTURES it as a flow leaf. The engine is built from config and
# constructor-injected by the stage (the builder fills its splitter); a default engine falls back to a
# TokenBudgetSplitter, so the node is runnable on its own.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.domain.ir.models.document_ir import DocumentIR
from common_libs.pipelines.core.ingest.stages.chunk.steps.chunk.chunker import (
    S4Result,
    StructureAwareChunker,
)
from common_libs.pipelines.flow import (
    ActionNode,
    Context,
    FromGroupInput,
    NodeInput,
    NodeOutput,
)


class ChunkNodeInput(NodeInput):
    """Input of the chunk node — the enriched IR, read from the chunk stage's own input."""

    ir: Annotated[DocumentIR, FromGroupInput()]


class ChunkNodeOutput(NodeOutput):
    """Output of the chunk node — the retrieval chunk list + the full chunk result."""

    chunks: list[Chunk]
    chunk_result: S4Result


class ChunkNode(ActionNode):
    """Structure-aware chunking — split the enriched IR into retrieval chunks via the chunking engine."""

    Input = ChunkNodeInput
    Output = ChunkNodeOutput

    def __init__(self, node_id: str, chunker: StructureAwareChunker | None = None) -> None:
        """
        Wire the node around the structure-aware chunking engine.

        Args:
            node_id (str): The node's id, unique among its siblings.
            chunker (StructureAwareChunker | None): The configured chunking engine (its splitter +
                heading rules + atomic policy + flat/hierarchical mode are assembly-time choices). None ->
                a default engine backed by a TokenBudgetSplitter.
        """
        super().__init__(node_id)
        self._chunker = chunker or StructureAwareChunker()

    async def execute(self, ctx: Context) -> ChunkNodeOutput:
        """
        Run the chunking engine over the enriched IR and return the chunk artefacts.

        Args:
            ctx (Context): Carries the resolved input (the enriched IR); the chunking engine is
                constructor-injected, so this node needs no service.

        Returns:
            ChunkNodeOutput: The chunk list + the full chunk result (config_hash + per-kind tallies).

        Raises:
            Exception: Propagated to the engine (wrapped into the node's failure report) when the
                structure-aware chunker fails for this document.
        """
        # 1. Run the deterministic structure-aware chunker over the enriched IR.
        ir = ctx.input.ir
        try:
            result = await self._chunker.run(ir)
        except Exception as exc:
            self.logger.error(f"Chunking failed for doc_id={ir.doc_id!r}: {exc}")
            raise

        # 2. Surface the chunk list and the full chunk result downstream.
        self.logger.info(f"Chunk node produced {len(result.chunks)} chunks for doc_id={ir.doc_id!r}.")
        return ChunkNodeOutput(chunks=result.chunks, chunk_result=result)


__all__ = ["ChunkNode", "ChunkNodeInput", "ChunkNodeOutput"]

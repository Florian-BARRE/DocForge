# ====== Code Summary ======
# The chunk stage — a GROUP holding a SINGLE action node (structure-aware chunking). Its typed Input
# binds the enriched IR to the enrich stage's output (the inter-stage spine), and its Output IS the
# single node's output (the default assemble = terminal), surfacing the retrieval chunks + the chunk
# result downstream to contextualize/embed. The chunking engine is built from the per-collection config
# and injected into the node by the builder; the stage itself holds no I/O.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.models.document_ir import DocumentIR
from common_libs.pipelines.core.ingest.stages.chunk.steps.chunk.chunker import StructureAwareChunker
from common_libs.pipelines.flow import FromNode, GroupNode, NodeInput

# ====== Local Project Imports ======
from .nodes import ChunkNode, ChunkNodeOutput


class ChunkStageInput(NodeInput):
    """The chunk stage input — the enriched IR produced by the enrich stage."""

    ir: Annotated[DocumentIR, FromNode("enrich", "ir")]


class ChunkStage(GroupNode):
    """Chunk: split the enriched IR into retrieval chunks via a single structure-aware chunk node."""

    Input = ChunkStageInput
    Output = ChunkNodeOutput  # single node -> the node's output IS the stage output (default assemble)

    def __init__(self, chunker: StructureAwareChunker | None = None) -> None:
        """
        Wire the single chunk node (no transitions — a one-node group).

        Args:
            chunker (StructureAwareChunker | None): The configured chunking engine, built from the
                per-collection config by the builder. None -> the node uses a default engine backed by a
                TokenBudgetSplitter.
        """
        super().__init__("chunk", [ChunkNode("chunk", chunker)], [])


__all__ = ["ChunkStage", "ChunkStageInput"]

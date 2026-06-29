# ====== Code Summary ======
# IO contract for the chunk step: it reads the enriched IR from its parent stage input (FromParent)
# and produces the retrieval chunk list + the chunk result (S4Result, carrying the deterministic
# config hash and per-kind tallies). These are the two artefacts the chunk stage surfaces downstream.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines import FromParent, NodeInput, NodeOutput

# ====== Local Project Imports ======
from .chunker import S4Result


class IngestStageChunkStepChunkInput(NodeInput):
    """
    Input of the chunk step (read from the parent stage input).

    Attributes:
        ir (DocumentIR): The enriched canonical IR to split into chunks.
    """

    ir: Annotated[DocumentIR, FromParent()]


class IngestStageChunkStepChunkOutput(NodeOutput):
    """
    Output of the chunk step.

    Attributes:
        chunks (list[Chunk]): Retrieval chunks in reading order (raw_text + prov.heading_path set).
        chunk_result (S4Result): The full chunking result (config_hash + per-kind tallies).
    """

    chunks: list[Chunk]
    chunk_result: S4Result


__all__ = [
    "IngestStageChunkStepChunkInput",
    "IngestStageChunkStepChunkOutput",
]

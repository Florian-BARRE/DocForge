# ====== Code Summary ======
# IO contract for the chunk stage: its input is the enriched IR (pulled from the enrich stage's
# output); its output is the assembled result of its single step — the retrieval chunk list and the
# chunk result (S4Result, carrying the deterministic config hash) consumed by contextualize/embed.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain.ir.chunk import Chunk
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipelines import FromSibling, NodeInput, NodeOutput

# ====== Local Project Imports ======
from .steps.chunk.chunker import S4Result


class IngestStageChunkInput(NodeInput):
    """
    Input of the chunk stage.

    Attributes:
        ir (DocumentIR): The enriched canonical IR, read from the enrich stage's output.
    """

    ir: Annotated[DocumentIR, FromSibling(producer="enrich", field="ir")]


class IngestStageChunkOutput(NodeOutput):
    """
    Output of the chunk stage — the assembled result of its single step.

    Attributes:
        chunks (list[Chunk]): Retrieval chunks in reading order (raw_text + prov.heading_path set).
        chunk_result (S4Result): The full chunking result (config_hash + per-kind tallies).
    """

    chunks: list[Chunk]
    chunk_result: S4Result


__all__ = ["IngestStageChunkInput", "IngestStageChunkOutput"]

# ====== Code Summary ======
# IO contract for the contextualize stage: it consumes the chunk list (from the chunk stage) and the
# enriched IR (from the enrich stage) via FromSibling, and produces the same chunk list with each
# chunk's embed_text populated, plus the contextualization tally. The IR is read only for its title;
# the chunks are mutated in place and returned so embed_index reads the contextualized chunks.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain import Chunk, DocumentIR
from common_libs.pipelines import FromSibling, NodeInput, NodeOutput

# ====== Local Project Imports ======
from .result import IngestStageContextualizeResult


class IngestStageContextualizeInput(NodeInput):
    """
    Input of the contextualize stage.

    Attributes:
        chunks (list[Chunk]): The chunk list produced by the chunk stage (embed_text empty on entry).
        ir (DocumentIR): The enriched IR for the same document (read for its title only).
    """

    chunks: Annotated[list[Chunk], FromSibling(producer="chunk", field="chunks")]
    ir: Annotated[DocumentIR, FromSibling(producer="enrich", field="ir")]


class IngestStageContextualizeOutput(NodeOutput):
    """
    Output of the contextualize stage — the contextualized chunks plus the tally.

    Attributes:
        chunks (list[Chunk]): The chunks with ``embed_text`` populated.
        contextualize_result (IngestStageContextualizeResult): Contextualization tally.
    """

    chunks: list[Chunk]
    contextualize_result: IngestStageContextualizeResult


__all__ = [
    "IngestStageContextualizeInput",
    "IngestStageContextualizeOutput",
]

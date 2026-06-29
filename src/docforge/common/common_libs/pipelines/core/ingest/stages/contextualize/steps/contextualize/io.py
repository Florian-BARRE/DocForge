# ====== Code Summary ======
# IO contract for the contextualize step: it reads the chunk list and the IR from its parent stage
# input (FromParent) and produces the same chunk list with each chunk's embed_text populated, plus the
# contextualization tally.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain import Chunk, DocumentIR
from common_libs.pipelines import FromParent, NodeInput, NodeOutput

# ====== Local Project Imports ======
from ...result import IngestStageContextualizeResult


class IngestStageContextualizeStepContextualizeInput(NodeInput):
    """
    Input of the contextualize step (all read from the parent stage input).

    Attributes:
        chunks (list[Chunk]): The chunk list (embed_text empty on entry).
        ir (DocumentIR): The enriched IR for the same document (read for its title only).
    """

    chunks: Annotated[list[Chunk], FromParent()]
    ir: Annotated[DocumentIR, FromParent()]


class IngestStageContextualizeStepContextualizeOutput(NodeOutput):
    """
    Output of the contextualize step.

    Attributes:
        chunks (list[Chunk]): The chunks with ``embed_text`` populated.
        contextualize_result (IngestStageContextualizeResult): Contextualization tally.
    """

    chunks: list[Chunk]
    contextualize_result: IngestStageContextualizeResult


__all__ = [
    "IngestStageContextualizeStepContextualizeInput",
    "IngestStageContextualizeStepContextualizeOutput",
]

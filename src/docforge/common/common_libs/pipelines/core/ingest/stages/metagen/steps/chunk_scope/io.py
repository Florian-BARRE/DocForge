# ====== Code Summary ======
# IO contract for the chunk-scope step: it reads the chunks from the parent stage input and the
# proceed flag from the budget-gate sibling, and produces the same chunks (with chunk-scope generated
# values written into each ``chunk.derived_meta``), the count of values written, and one representative
# chain trace. When proceed is False it passes the chunks through unchanged.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain import Chunk, ChainTrace
from common_libs.pipelines import FromParent, FromSibling, NodeInput, NodeOutput


class IngestStageMetagenStepChunkScopeInput(NodeInput):
    """
    Input of the chunk-scope step.

    Attributes:
        chunks (list[Chunk]): The document's chunks (from the parent stage input).
        proceed (bool): The budget-gate decision (from the budget-gate step).
    """

    chunks: Annotated[list[Chunk], FromParent()]
    proceed: Annotated[bool, FromSibling(producer="budget_gate", field="proceed")]


class IngestStageMetagenStepChunkScopeOutput(NodeOutput):
    """
    Output of the chunk-scope step.

    Attributes:
        chunks (list[Chunk]): The same chunks, with chunk-scope generated values written into each
            ``chunk.derived_meta`` (mutated in place).
        n_generated (int): Count of chunk-scope generated values written.
        chain_trace (ChainTrace | None): One representative trace (first real, non-cached call), or
            None when nothing ran.
    """

    chunks: list[Chunk]
    n_generated: int = 0
    chain_trace: ChainTrace | None = None


__all__ = [
    "IngestStageMetagenStepChunkScopeInput",
    "IngestStageMetagenStepChunkScopeOutput",
]

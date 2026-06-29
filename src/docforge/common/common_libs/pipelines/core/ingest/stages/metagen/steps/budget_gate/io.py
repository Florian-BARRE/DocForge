# ====== Code Summary ======
# IO contract for the budget-gate step: it reads the chunks + IR from the parent stage input, then
# decides whether the metagen scopes run. ``proceed`` is False on a complete no-op (no provider, no
# resolvable target) or when the estimated spend exceeds the per-document budget; ``est_cost_usd`` is
# the estimate carried into the result either way.

# ====== Standard Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.domain import Chunk, DocumentIR
from common_libs.pipelines import FromParent, NodeInput, NodeOutput


class IngestStageMetagenStepBudgetGateInput(NodeInput):
    """
    Input of the budget-gate step (read from the parent stage input).

    Attributes:
        chunks (list[Chunk]): The document's chunks (chunk-scope cost driver).
        ir (DocumentIR): The final IR (document-scope digest source).
    """

    chunks: Annotated[list[Chunk], FromParent()]
    ir: Annotated[DocumentIR, FromParent()]


class IngestStageMetagenStepBudgetGateOutput(NodeOutput):
    """
    Output of the budget-gate step.

    Attributes:
        proceed (bool): True when the metagen scopes should run; False on a no-op or over-budget.
        est_cost_usd (float): Estimated LLM spend for this document's metagen calls.
    """

    proceed: bool
    est_cost_usd: float = 0.0


__all__ = [
    "IngestStageMetagenStepBudgetGateInput",
    "IngestStageMetagenStepBudgetGateOutput",
]

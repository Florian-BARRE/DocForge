# ====== Code Summary ======
# The budget-gate step's own failure type — raised on an unexpected error while estimating cost or
# consulting the chain. The gate itself never fails the document for being over budget (it returns
# proceed=False); this error is reserved for genuine faults.

# ====== Internal Project Imports ======
from ..base import IngestStageMetagenStepError


class IngestStageMetagenStepBudgetGateError(IngestStageMetagenStepError):
    """Raised when the budget-gate step fails unexpectedly."""

    code = "metagen_budget_gate_failed"
    description = "The metagen budget-gate step failed to evaluate the per-document spend."


__all__ = ["IngestStageMetagenStepBudgetGateError"]

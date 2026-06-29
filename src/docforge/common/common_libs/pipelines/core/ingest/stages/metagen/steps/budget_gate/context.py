# ====== Code Summary ======
# The budget-gate step's context — narrows ``input`` to this step's typed input and exposes the LLM
# chain it requires as a typed accessor (``ctx.llm_chain``). The chain is consulted only for its
# provider list (the no-op short-circuit); no LLM call is issued by this step.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from common_libs.pipelines.capabilities.chain import Chain

# ====== Local Project Imports ======
from ..base import IngestStageMetagenStepContextBase
from .io import IngestStageMetagenStepBudgetGateInput


class IngestStageMetagenStepBudgetGateContext(IngestStageMetagenStepContextBase):
    """Context for the budget-gate step (typed input + the LLM chain)."""

    @property
    def input(self) -> IngestStageMetagenStepBudgetGateInput:
        """The step's typed input."""
        return self._input

    @property
    def llm_chain(self) -> Chain[Any, Any]:
        """The injected LLM provider chain (consulted for its provider list only)."""
        return self.service("llm_chain")


__all__ = ["IngestStageMetagenStepBudgetGateContext"]

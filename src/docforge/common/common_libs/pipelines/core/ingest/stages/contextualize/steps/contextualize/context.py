# ====== Code Summary ======
# The contextualize step's context — narrows ``input`` to this step's typed input. This is the
# PURE-LOGIC step case: it requires no service (no provider chain, no infra client), so the context
# only exposes the typed input.

# ====== Local Project Imports ======
from ..base import IngestStageContextualizeStepContextBase
from .io import IngestStageContextualizeStepContextualizeInput


class IngestStageContextualizeStepContextualizeContext(IngestStageContextualizeStepContextBase):
    """Context for the contextualize step (typed input only — no service)."""

    @property
    def input(self) -> IngestStageContextualizeStepContextualizeInput:
        """The step's typed input."""
        return self._input


__all__ = ["IngestStageContextualizeStepContextualizeContext"]

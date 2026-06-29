# ====== Code Summary ======
# The contextualize stage's context — narrows ``input`` to the stage input. The stage itself requires
# no service (its single pure step requires none either); this context exists for hierarchy + typed
# input access.

# ====== Local Project Imports ======
from ..base import IngestStageContextBase
from .io import IngestStageContextualizeInput


class IngestStageContextualizeContext(IngestStageContextBase):
    """Context for the contextualize stage (typed input)."""

    @property
    def input(self) -> IngestStageContextualizeInput:
        """The stage's typed input."""
        return self._input


__all__ = ["IngestStageContextualizeContext"]

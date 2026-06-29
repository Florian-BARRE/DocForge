# ====== Code Summary ======
# The assemble-doc-meta step's context — narrows ``input`` to this step's typed input. The step is a
# pure merge over its resolved inputs and requires no service.

# ====== Local Project Imports ======
from ..base import IngestStageMetagenStepContextBase
from .io import IngestStageMetagenStepAssembleDocMetaInput


class IngestStageMetagenStepAssembleDocMetaContext(IngestStageMetagenStepContextBase):
    """Context for the assemble-doc-meta step (typed input only)."""

    @property
    def input(self) -> IngestStageMetagenStepAssembleDocMetaInput:
        """The step's typed input."""
        return self._input


__all__ = ["IngestStageMetagenStepAssembleDocMetaContext"]

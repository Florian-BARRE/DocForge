# ====== Code Summary ======
# The assemble_points step's context — narrows ``input`` to this step's typed input. The step is pure
# (it assembles the named-vector maps + Qdrant payloads in memory) and requires no service.

# ====== Local Project Imports ======
from ..base import IngestStageEmbedIndexStepContextBase
from .io import IngestStageEmbedIndexStepAssemblePointsInput


class IngestStageEmbedIndexStepAssemblePointsContext(IngestStageEmbedIndexStepContextBase):
    """Context for the assemble_points step (typed input only)."""

    @property
    def input(self) -> IngestStageEmbedIndexStepAssemblePointsInput:
        """The step's typed input."""
        return self._input


__all__ = ["IngestStageEmbedIndexStepAssemblePointsContext"]

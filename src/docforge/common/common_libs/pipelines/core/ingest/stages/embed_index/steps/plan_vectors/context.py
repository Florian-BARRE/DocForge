# ====== Code Summary ======
# The plan_vectors step's context — narrows ``input`` to this step's typed input. The step is pure
# (it derives the vector plan from the metadata schema) and requires no service.

# ====== Local Project Imports ======
from ..base import IngestStageEmbedIndexStepContextBase
from .io import IngestStageEmbedIndexStepPlanVectorsInput


class IngestStageEmbedIndexStepPlanVectorsContext(IngestStageEmbedIndexStepContextBase):
    """Context for the plan_vectors step (typed input only)."""

    @property
    def input(self) -> IngestStageEmbedIndexStepPlanVectorsInput:
        """The step's typed input."""
        return self._input


__all__ = ["IngestStageEmbedIndexStepPlanVectorsContext"]

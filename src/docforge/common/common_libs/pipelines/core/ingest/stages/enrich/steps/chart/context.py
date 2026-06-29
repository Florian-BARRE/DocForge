# ====== Code Summary ======
# The chart step's context - narrows ``input`` to the chart input. The step requires no service (it
# only post-processes the VLM structured output already on each FigureWork), so the context carries
# typed input only.

# ====== Local Project Imports ======
from ..base import IngestStageEnrichStepContextBase
from .io import IngestStageEnrichStepChartInput


class IngestStageEnrichStepChartContext(IngestStageEnrichStepContextBase):
    """Context for the chart step (typed input only)."""

    @property
    def input(self) -> IngestStageEnrichStepChartInput:
        """The step's typed input."""
        return self._input


__all__ = ["IngestStageEnrichStepChartContext"]

# ====== Code Summary ======
# The probe step's context — narrows ``input`` to the probe input. The step requires no service, so
# the context only carries typed input.

# ====== Local Project Imports ======
from ..base import IngestStageIngestStepContextBase
from .io import IngestStageIngestStepProbeInput


class IngestStageIngestStepProbeContext(IngestStageIngestStepContextBase):
    """Context for the probe step (typed input only)."""

    @property
    def input(self) -> IngestStageIngestStepProbeInput:
        """The step's typed input."""
        return self._input


__all__ = ["IngestStageIngestStepProbeContext"]

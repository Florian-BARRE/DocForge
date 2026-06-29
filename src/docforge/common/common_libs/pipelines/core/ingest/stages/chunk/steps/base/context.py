# ====== Code Summary ======
# IngestStageChunkStepContextBase — the base context shared by every step of the chunk stage.
# Concrete step contexts subclass it to narrow ``input``. It is the step-level node of the context
# hierarchy for this stage.

# ====== Internal Project Imports ======
from common_libs.pipelines import StepContextBase


class IngestStageChunkStepContextBase(StepContextBase):
    """Base context for every step of the chunk stage."""


__all__ = ["IngestStageChunkStepContextBase"]

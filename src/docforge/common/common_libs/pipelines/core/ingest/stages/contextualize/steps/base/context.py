# ====== Code Summary ======
# IngestStageContextualizeStepContextBase — the base context shared by every step of the contextualize
# stage. Concrete step contexts subclass it to narrow ``input``. It is the step-level node of the
# context hierarchy for this stage.

# ====== Internal Project Imports ======
from common_libs.pipelines import StepContextBase


class IngestStageContextualizeStepContextBase(StepContextBase):
    """Base context for every step of the contextualize stage."""


__all__ = ["IngestStageContextualizeStepContextBase"]

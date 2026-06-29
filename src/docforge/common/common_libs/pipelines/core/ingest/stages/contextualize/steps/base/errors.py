# ====== Code Summary ======
# IngestStageContextualizeStepError — the base error for every step of the contextualize stage.
# Concrete steps subclass it so the feedback tree carries a precise, step-specific code while staying
# within the contextualize stage's error family.

# ====== Internal Project Imports ======
from common_libs.pipelines import StepError


class IngestStageContextualizeStepError(StepError):
    """Base for failures raised by a step of the contextualize stage."""

    code = "contextualize_step_error"
    description = "A step of the contextualize stage failed."


__all__ = ["IngestStageContextualizeStepError"]

# ====== Code Summary ======
# IngestStageMetagenStepError — the base error for every step of the metagen stage. Concrete steps
# subclass it (e.g. a budget-gate failure, a generation failure) so the feedback tree carries a
# precise, step-specific code while staying within the metagen stage's error family.

# ====== Internal Project Imports ======
from common_libs.pipelines import StepError


class IngestStageMetagenStepError(StepError):
    """Base for failures raised by a step of the metagen stage."""

    code = "metagen_step_error"
    description = "A step of the metagen stage failed."


__all__ = ["IngestStageMetagenStepError"]

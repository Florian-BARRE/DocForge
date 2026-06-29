# ====== Code Summary ======
# IngestStageParseStepError — the base error for every step of the parse stage. Concrete steps
# subclass it (a fetch failure, a parse failure, a markdown upload failure) so the feedback tree
# carries a precise, step-specific code while staying within the parse stage's error family.

# ====== Internal Project Imports ======
from common_libs.pipelines import StepError


class IngestStageParseStepError(StepError):
    """Base for failures raised by a step of the parse stage."""

    code = "parse_step_error"
    description = "A step of the parse stage failed."


__all__ = ["IngestStageParseStepError"]

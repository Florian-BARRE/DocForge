# ====== Code Summary ======
# IngestStageEnrichStepError - the base error for every step of the enrich stage. Concrete steps
# subclass it (e.g. a classify failure, an OCR failure) so the feedback tree carries a precise,
# step-specific code while staying within the enrich stage's error family.

# ====== Internal Project Imports ======
from common_libs.pipelines import StepError


class IngestStageEnrichStepError(StepError):
    """Base for failures raised by a step of the enrich stage."""

    code = "enrich_step_error"
    description = "A step of the enrich stage failed."


__all__ = ["IngestStageEnrichStepError"]

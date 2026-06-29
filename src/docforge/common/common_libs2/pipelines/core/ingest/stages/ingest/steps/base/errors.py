# ====== Code Summary ======
# IngestStageIngestStepError — the base error for every step of the ingest stage. Concrete steps
# subclass it (e.g. an upload failure, a conversion failure) so the feedback tree carries a precise,
# step-specific code while staying within the ingest stage's error family.

# ====== Internal Project Imports ======
from common_libs2.pipelines import StepError


class IngestStageIngestStepError(StepError):
    """Base for failures raised by a step of the ingest stage."""

    code = "ingest_step_error"
    description = "A step of the ingest stage failed."


__all__ = ["IngestStageIngestStepError"]

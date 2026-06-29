# ====== Code Summary ======
# IngestStageChunkStepError — the base error for every step of the chunk stage. Concrete steps
# subclass it so the feedback tree carries a precise, step-specific code while staying within the
# chunk stage's error family.

# ====== Internal Project Imports ======
from common_libs.pipelines import StepError


class IngestStageChunkStepError(StepError):
    """Base for failures raised by a step of the chunk stage."""

    code = "chunk_step_error"
    description = "A step of the chunk stage failed."


__all__ = ["IngestStageChunkStepError"]

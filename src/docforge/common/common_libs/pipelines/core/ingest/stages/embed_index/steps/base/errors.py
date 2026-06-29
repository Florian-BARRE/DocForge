# ====== Code Summary ======
# IngestStageEmbedIndexStepError — the base error for every step of the embed_index stage. Concrete
# steps subclass it (e.g. a Qdrant upsert failure, a Postgres persist failure) so the feedback tree
# carries a precise, step-specific code while staying within the embed_index stage's error family.

# ====== Internal Project Imports ======
from common_libs.pipelines import StepError


class IngestStageEmbedIndexStepError(StepError):
    """Base for failures raised by a step of the embed_index stage."""

    code = "embed_index_step_error"
    description = "A step of the embed_index stage failed."


__all__ = ["IngestStageEmbedIndexStepError"]

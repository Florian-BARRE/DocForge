# ====== Code Summary ======
# The plan_vectors step's own failure type — raised when the vector plan cannot be derived from the
# collection metadata schema. Carries a precise code so the feedback tree pinpoints this step.

# ====== Internal Project Imports ======
from ..base import IngestStageEmbedIndexStepError


class IngestStageEmbedIndexStepPlanVectorsError(IngestStageEmbedIndexStepError):
    """Raised when the vector plan cannot be derived from the metadata schema."""

    code = "embed_index_plan_vectors_failed"
    description = "The vector plan could not be derived from the collection metadata schema."


__all__ = ["IngestStageEmbedIndexStepPlanVectorsError"]

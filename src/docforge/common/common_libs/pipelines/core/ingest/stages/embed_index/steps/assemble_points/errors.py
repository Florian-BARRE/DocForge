# ====== Code Summary ======
# The assemble_points step's own failure type — raised when the named-vector maps or the Qdrant
# payloads cannot be assembled. Carries a precise code so the feedback tree pinpoints this step.

# ====== Internal Project Imports ======
from ..base import IngestStageEmbedIndexStepError


class IngestStageEmbedIndexStepAssemblePointsError(IngestStageEmbedIndexStepError):
    """Raised when the Qdrant point vectors/payloads cannot be assembled."""

    code = "embed_index_assemble_points_failed"
    description = "The Qdrant named-vector maps or payloads could not be assembled."


__all__ = ["IngestStageEmbedIndexStepAssemblePointsError"]

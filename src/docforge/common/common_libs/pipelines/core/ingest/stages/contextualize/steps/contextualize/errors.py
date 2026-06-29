# ====== Code Summary ======
# The contextualize step's own failure type — raised when embed_text assembly fails for a chunk.
# Pure logic, so a failure is not expected to be transient; it is not marked retryable. Carries a
# precise code so the feedback tree pinpoints this step within the contextualize stage's error family.

# ====== Internal Project Imports ======
from ..base import IngestStageContextualizeStepError


class IngestStageContextualizeStepContextualizeError(IngestStageContextualizeStepError):
    """Raised when a chunk's embed_text cannot be assembled."""

    code = "contextualize_embed_text_failed"
    description = "A chunk's embed_text could not be assembled."


__all__ = ["IngestStageContextualizeStepContextualizeError"]

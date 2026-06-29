# ====== Code Summary ======
# IngestStageContextualizeError — the contextualize stage's own error family (parent of its step
# error). Kept as a distinct node of the error hierarchy so a failure can be attributed to this stage.

# ====== Internal Project Imports ======
from ..base import IngestStageError


class IngestStageContextualizeError(IngestStageError):
    """Base for failures attributed to the contextualize stage."""

    code = "ingest_contextualize_stage_error"
    description = "The contextualize stage (embed_text assembly) failed."


__all__ = ["IngestStageContextualizeError"]

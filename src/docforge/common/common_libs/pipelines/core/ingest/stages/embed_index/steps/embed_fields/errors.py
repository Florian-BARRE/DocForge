# ====== Code Summary ======
# The embed_fields step's own failure type — raised when the embed chain cannot produce metadata
# field vectors. Carries a precise code so the feedback tree pinpoints this step; the chain itself
# raises ChainExhaustedError under failure_policy="raise", which the engine wraps in this step's error.

# ====== Internal Project Imports ======
from ..base import IngestStageEmbedIndexStepError


class IngestStageEmbedIndexStepEmbedFieldsError(IngestStageEmbedIndexStepError):
    """Raised when the embed chain fails to embed the metadata field values."""

    code = "embed_index_embed_fields_failed"
    description = "The embed chain failed to embed the metadata field values."
    retryable = True


__all__ = ["IngestStageEmbedIndexStepEmbedFieldsError"]

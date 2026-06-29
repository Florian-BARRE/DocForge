# ====== Code Summary ======
# The embed_content step's own failure type — raised when the embed chain cannot produce content
# vectors. Carries a precise code so the feedback tree pinpoints this step; the chain itself raises
# ChainExhaustedError under failure_policy="raise", which the engine wraps in this step's error.

# ====== Internal Project Imports ======
from ..base import IngestStageEmbedIndexStepError


class IngestStageEmbedIndexStepEmbedContentError(IngestStageEmbedIndexStepError):
    """Raised when the embed chain fails to embed the chunk bodies."""

    code = "embed_index_embed_content_failed"
    description = "The embed chain failed to embed the chunk bodies."
    retryable = True


__all__ = ["IngestStageEmbedIndexStepEmbedContentError"]

# ====== Code Summary ======
# The chunk step's own failure type — raised when structure-aware chunking fails. Carries a precise
# code so the feedback tree pinpoints this step; not retryable since a deterministic chunking failure
# (bad IR shape, splitter error) will not succeed on a blind retry.

# ====== Local Project Imports ======
from ..base import IngestStageChunkStepError


class IngestStageChunkStepChunkError(IngestStageChunkStepError):
    """Raised when the enriched IR cannot be split into chunks."""

    code = "chunk_chunking_failed"
    description = "The enriched IR could not be split into retrieval chunks."
    retryable = False


__all__ = ["IngestStageChunkStepChunkError"]

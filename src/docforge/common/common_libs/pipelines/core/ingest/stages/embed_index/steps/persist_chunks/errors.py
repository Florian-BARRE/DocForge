# ====== Code Summary ======
# The persist_chunks step's own failure type — raised when the chunk rows cannot be persisted to
# Postgres. Carries a precise code; marked retryable since a database hiccup is typically transient.

# ====== Internal Project Imports ======
from ..base import IngestStageEmbedIndexStepError


class IngestStageEmbedIndexStepPersistChunksError(IngestStageEmbedIndexStepError):
    """Raised when the chunk rows cannot be persisted to Postgres."""

    code = "embed_index_persist_chunks_failed"
    description = "The chunk rows could not be persisted to Postgres."
    retryable = True


__all__ = ["IngestStageEmbedIndexStepPersistChunksError"]

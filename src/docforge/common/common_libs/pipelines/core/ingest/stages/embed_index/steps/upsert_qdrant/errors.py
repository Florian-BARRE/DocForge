# ====== Code Summary ======
# The upsert_qdrant step's own failure type — raised when the Qdrant collection cannot be ensured or
# the points cannot be upserted. Carries a precise code; marked retryable since a Qdrant hiccup is
# typically transient.

# ====== Internal Project Imports ======
from ..base import IngestStageEmbedIndexStepError


class IngestStageEmbedIndexStepUpsertQdrantError(IngestStageEmbedIndexStepError):
    """Raised when the Qdrant collection cannot be ensured or the points cannot be upserted."""

    code = "embed_index_upsert_qdrant_failed"
    description = "The multi-vector points could not be upserted to Qdrant."
    retryable = True


__all__ = ["IngestStageEmbedIndexStepUpsertQdrantError"]

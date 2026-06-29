# ====== Code Summary ======
# IngestStageEmbedIndexError — the embed_index stage's own error family (parent of its step errors).
# Kept as a distinct node of the error hierarchy so a failure can be attributed to this stage.

# ====== Internal Project Imports ======
from ..base import IngestStageError


class IngestStageEmbedIndexError(IngestStageError):
    """Base for failures attributed to the embed_index stage."""

    code = "ingest_embed_index_stage_error"
    description = "The embed_index stage (embed / Qdrant upsert / Postgres persist) failed."


__all__ = ["IngestStageEmbedIndexError"]

# ====== Code Summary ======
# IngestStageChunkError — the chunk stage's own error family (parent of its step errors). Kept as a
# distinct node of the error hierarchy so a failure can be attributed to this stage specifically.

# ====== Internal Project Imports ======
from ..base import IngestStageError


class IngestStageChunkError(IngestStageError):
    """Base for failures attributed to the chunk stage."""

    code = "ingest_chunk_stage_error"
    description = "The chunk stage (structure-aware chunking) failed."


__all__ = ["IngestStageChunkError"]

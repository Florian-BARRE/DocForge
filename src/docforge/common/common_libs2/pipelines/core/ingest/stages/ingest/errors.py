# ====== Code Summary ======
# IngestStageIngestError — the ingest stage's own error family (parent of its step errors). Kept as a
# distinct node of the error hierarchy so a failure can be attributed to this stage specifically.

# ====== Internal Project Imports ======
from ..base import IngestStageError


class IngestStageIngestError(IngestStageError):
    """Base for failures attributed to the ingest stage."""

    code = "ingest_ingest_stage_error"
    description = "The ingest stage (content-address / convert / probe) failed."


__all__ = ["IngestStageIngestError"]

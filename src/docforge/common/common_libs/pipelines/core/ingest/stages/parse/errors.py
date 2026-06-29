# ====== Code Summary ======
# IngestStageParseError — the parse stage's own error family (parent of its step errors). Kept as a
# distinct node of the error hierarchy so a failure can be attributed to this stage specifically.

# ====== Local Project Imports ======
from ..base import IngestStageError


class IngestStageParseError(IngestStageError):
    """Base for failures attributed to the parse stage."""

    code = "ingest_parse_stage_error"
    description = "The parse stage (fetch-pdf / parse / figure-render / markdown) failed."


__all__ = ["IngestStageParseError"]

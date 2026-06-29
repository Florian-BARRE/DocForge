# ====== Code Summary ======
# IngestStageMetagenError — the metagen stage's own error family (parent of its step errors). Kept as
# a distinct node of the error hierarchy so a failure can be attributed to this stage specifically.

# ====== Internal Project Imports ======
from ..base import IngestStageError


class IngestStageMetagenError(IngestStageError):
    """Base for failures attributed to the metagen stage."""

    code = "ingest_metagen_stage_error"
    description = "The metagen stage (budget gate / chunk-scope / doc-scope / assemble) failed."


__all__ = ["IngestStageMetagenError"]

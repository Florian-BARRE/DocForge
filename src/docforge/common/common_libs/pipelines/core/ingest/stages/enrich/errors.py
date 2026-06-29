# ====== Code Summary ======
# IngestStageEnrichError - the enrich stage's own error family (parent of its step errors). Kept as a
# distinct node of the error hierarchy so a failure can be attributed to this stage specifically.

# ====== Internal Project Imports ======
from ..base import IngestStageError


class IngestStageEnrichError(IngestStageError):
    """Base for failures attributed to the enrich stage."""

    code = "ingest_enrich_stage_error"
    description = "The enrich stage (classify / OCR / VLM / chart) failed."


__all__ = ["IngestStageEnrichError"]

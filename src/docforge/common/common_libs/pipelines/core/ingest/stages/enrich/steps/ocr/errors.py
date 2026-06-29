# ====== Code Summary ======
# The OCR step's own failure type - raised when the OCR pass fails irrecoverably. Retryable, since
# the OCR providers and the object store can fail transiently.

# ====== Internal Project Imports ======
from ..base import IngestStageEnrichStepError


class IngestStageEnrichStepOcrError(IngestStageEnrichStepError):
    """Raised when the OCR pass fails."""

    code = "enrich_ocr_failed"
    description = "The enrich OCR pass (figure text extraction) failed."
    retryable = True


__all__ = ["IngestStageEnrichStepOcrError"]

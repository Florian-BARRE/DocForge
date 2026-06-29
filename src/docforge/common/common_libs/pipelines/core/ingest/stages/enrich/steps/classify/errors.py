# ====== Code Summary ======
# The classify step's own failure type - raised when crop classification fails irrecoverably. A
# single crop that fails to download is skipped (not an error); this error is reserved for a failure
# that should fail the figure-classification pass as a whole.

# ====== Internal Project Imports ======
from ..base import IngestStageEnrichStepError


class IngestStageEnrichStepClassifyError(IngestStageEnrichStepError):
    """Raised when the figure classification pass fails."""

    code = "enrich_classify_failed"
    description = "The enrich classify pass (figure classification) failed."
    retryable = True


__all__ = ["IngestStageEnrichStepClassifyError"]

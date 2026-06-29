# ====== Code Summary ======
# The VLM step's own failure type - raised when the VLM pass fails irrecoverably. Retryable, since
# the VLM providers can fail transiently.

# ====== Internal Project Imports ======
from ..base import IngestStageEnrichStepError


class IngestStageEnrichStepVlmError(IngestStageEnrichStepError):
    """Raised when the VLM pass fails."""

    code = "enrich_vlm_failed"
    description = "The enrich VLM pass (figure description) failed."
    retryable = True


__all__ = ["IngestStageEnrichStepVlmError"]

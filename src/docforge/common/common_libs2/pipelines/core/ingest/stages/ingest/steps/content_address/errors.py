# ====== Code Summary ======
# The content-address step's own failure type — raised when the original upload to the object store
# fails. Carries a precise code so the feedback tree pinpoints this step; marked retryable since an
# object-store hiccup is typically transient.

# ====== Internal Project Imports ======
from ..base import IngestStageIngestStepError


class IngestStageIngestStepContentAddressError(IngestStageIngestStepError):
    """Raised when the original file cannot be uploaded to the object store."""

    code = "content_address_upload_failed"
    description = "The original file could not be uploaded to the object store."
    retryable = True


__all__ = ["IngestStageIngestStepContentAddressError"]

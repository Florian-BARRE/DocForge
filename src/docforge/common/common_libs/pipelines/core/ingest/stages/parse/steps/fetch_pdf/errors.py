# ====== Code Summary ======
# The fetch-pdf step's own failure type — raised when the PDF view download from the object store
# fails. Retryable, since the object store can fail transiently.

# ====== Local Project Imports ======
from ..base import IngestStageParseStepError


class IngestStageParseStepFetchPdfError(IngestStageParseStepError):
    """Raised when the PDF view cannot be downloaded from the object store."""

    code = "fetch_pdf_failed"
    description = "The PDF view could not be downloaded from the object store."
    retryable = True


__all__ = ["IngestStageParseStepFetchPdfError"]

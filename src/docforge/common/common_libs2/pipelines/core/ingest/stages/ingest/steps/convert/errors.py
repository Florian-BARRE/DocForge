# ====== Code Summary ======
# The convert step's own failure type — raised when the office/HTML -> PDF conversion (or the PDF
# upload) fails. Retryable, since both the converter and the object store can fail transiently.

# ====== Internal Project Imports ======
from ..base import IngestStageIngestStepError


class IngestStageIngestStepConvertError(IngestStageIngestStepError):
    """Raised when conversion to PDF or the PDF upload fails."""

    code = "convert_failed"
    description = "The document could not be converted to PDF (or the PDF upload failed)."
    retryable = True


__all__ = ["IngestStageIngestStepConvertError"]

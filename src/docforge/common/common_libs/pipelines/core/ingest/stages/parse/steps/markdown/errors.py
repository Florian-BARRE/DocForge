# ====== Code Summary ======
# The markdown step's own failure type — raised when the serialised markdown view upload to the
# object store fails. Retryable, since the object store can fail transiently.

# ====== Local Project Imports ======
from ..base import IngestStageParseStepError


class IngestStageParseStepMarkdownError(IngestStageParseStepError):
    """Raised when the markdown view upload to the object store fails."""

    code = "markdown_upload_failed"
    description = "The serialised markdown view could not be uploaded to the object store."
    retryable = True


__all__ = ["IngestStageParseStepMarkdownError"]

# ====== Code Summary ======
# The figure-render step's own failure type — raised when uploading the rendered figure crops to the
# object store fails. Retryable, since the object store can fail transiently. Per-crop rendering
# failures are logged and skipped (never fatal), so this fires only on the upload boundary.

# ====== Local Project Imports ======
from ..base import IngestStageParseStepError


class IngestStageParseStepFigureRenderError(IngestStageParseStepError):
    """Raised when uploading the rendered figure crops to the object store fails."""

    code = "figure_render_failed"
    description = "The rendered figure crops could not be uploaded to the object store."
    retryable = True


__all__ = ["IngestStageParseStepFigureRenderError"]

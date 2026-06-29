# ====== Code Summary ======
# The figure-render step's context — narrows ``input`` and exposes the real object-store client it
# requires (``S3Client``) for the deduplicated crop uploads.

# ====== Internal Project Imports ======
from common_libs.storage.s3.client import S3Client

# ====== Local Project Imports ======
from ..base import IngestStageParseStepContextBase
from .io import IngestStageParseStepFigureRenderInput


class IngestStageParseStepFigureRenderContext(IngestStageParseStepContextBase):
    """Context for the figure-render step (typed input + the real object store)."""

    @property
    def input(self) -> IngestStageParseStepFigureRenderInput:
        """The step's typed input."""
        return self._input

    @property
    def object_store(self) -> S3Client:
        """The SeaweedFS S3 client the figure crops are uploaded to."""
        return self.service("object_store")


__all__ = ["IngestStageParseStepFigureRenderContext"]

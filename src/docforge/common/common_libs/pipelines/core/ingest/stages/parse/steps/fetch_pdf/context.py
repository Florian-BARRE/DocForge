# ====== Code Summary ======
# The fetch-pdf step's context — narrows ``input`` and exposes the real object-store client it
# requires (``S3Client``). The object store is infrastructure (one real client), injected as a
# service — not abstracted behind a port.

# ====== Internal Project Imports ======
from common_libs.storage.s3.client import S3Client

# ====== Local Project Imports ======
from ..base import IngestStageParseStepContextBase
from .io import IngestStageParseStepFetchPdfInput


class IngestStageParseStepFetchPdfContext(IngestStageParseStepContextBase):
    """Context for the fetch-pdf step (typed input + the real object store)."""

    @property
    def input(self) -> IngestStageParseStepFetchPdfInput:
        """The step's typed input."""
        return self._input

    @property
    def object_store(self) -> S3Client:
        """The SeaweedFS S3 client the PDF view is downloaded from."""
        return self.service("object_store")


__all__ = ["IngestStageParseStepFetchPdfContext"]

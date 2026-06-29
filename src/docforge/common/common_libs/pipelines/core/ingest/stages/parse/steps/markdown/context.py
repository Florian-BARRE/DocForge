# ====== Code Summary ======
# The markdown step's context — narrows ``input`` and exposes the two services it requires: the object
# store (``S3Client``) the markdown blob is uploaded to, and the markdown serialiser
# (``MarkdownSerializer``) that renders the canonical IR to its faithful markdown view.

# ====== Internal Project Imports ======
from common_libs.domain.ir.serializer import MarkdownSerializer
from common_libs.storage.s3.client import S3Client

# ====== Local Project Imports ======
from ..base import IngestStageParseStepContextBase
from .io import IngestStageParseStepMarkdownInput


class IngestStageParseStepMarkdownContext(IngestStageParseStepContextBase):
    """Context for the markdown step (typed input + object store + serialiser)."""

    @property
    def input(self) -> IngestStageParseStepMarkdownInput:
        """The step's typed input."""
        return self._input

    @property
    def object_store(self) -> S3Client:
        """The SeaweedFS S3 client the markdown view is uploaded to."""
        return self.service("object_store")

    @property
    def serializer(self) -> MarkdownSerializer:
        """The serialiser that renders the canonical IR to faithful markdown."""
        return self.service("serializer")


__all__ = ["IngestStageParseStepMarkdownContext"]

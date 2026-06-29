# ====== Code Summary ======
# The convert step's context — narrows ``input`` and exposes the two real services it requires: the
# object store (``S3Client``) and the converter (``ConverterProvider``, the existing common_libs
# interface; the concrete Gotenberg client is injected at assembly).

# ====== Internal Project Imports ======
from common_libs.providers.interfaces.converter_provider import ConverterProvider
from common_libs.storage.s3.client import S3Client

# ====== Local Project Imports ======
from ..base import IngestStageIngestStepContextBase
from .io import IngestStageIngestStepConvertInput


class IngestStageIngestStepConvertContext(IngestStageIngestStepContextBase):
    """Context for the convert step (typed input + object store + converter)."""

    @property
    def input(self) -> IngestStageIngestStepConvertInput:
        """The step's typed input."""
        return self._input

    @property
    def object_store(self) -> S3Client:
        """The SeaweedFS S3 client the PDF view is uploaded to."""
        return self.service("object_store")

    @property
    def converter(self) -> ConverterProvider:
        """The office/HTML -> PDF converter (Gotenberg in production)."""
        return self.service("converter")


__all__ = ["IngestStageIngestStepConvertContext"]

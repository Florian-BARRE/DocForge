# ====== Code Summary ======
# The content-address step's context — narrows ``input`` to this step's typed input and exposes the
# real object-store client it requires as a typed accessor (``ctx.object_store``). The object store
# is infrastructure (one real ``S3Client``), injected as a service — not abstracted behind a port.

# ====== Internal Project Imports ======
from common_libs.storage.s3.client import S3Client

# ====== Local Project Imports ======
from ..base import IngestStageIngestStepContextBase
from .io import IngestStageIngestStepContentAddressInput


class IngestStageIngestStepContentAddressContext(IngestStageIngestStepContextBase):
    """Context for the content-address step (typed input + the real object store)."""

    @property
    def input(self) -> IngestStageIngestStepContentAddressInput:
        """The step's typed input."""
        return self._input

    @property
    def object_store(self) -> S3Client:
        """The SeaweedFS S3 client the original is uploaded to."""
        return self.service("object_store")


__all__ = ["IngestStageIngestStepContentAddressContext"]

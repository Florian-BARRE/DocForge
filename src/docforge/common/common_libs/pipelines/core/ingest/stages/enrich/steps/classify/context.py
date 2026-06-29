# ====== Code Summary ======
# The classify step's context - narrows ``input`` and exposes the three real services it requires:
# the classifier chain (the ordered figure classifier providers), the object store (``S3Client`` for
# crop downloads), and the cross-document provider-call cache.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from common_libs.pipelines.bricks.caches import ProviderCallCache
from common_libs.pipelines.bricks.chain import Chain
from common_libs.storage.s3.client import S3Client

# ====== Local Project Imports ======
from ..base import IngestStageEnrichStepContextBase
from .io import IngestStageEnrichStepClassifyInput


class IngestStageEnrichStepClassifyContext(IngestStageEnrichStepContextBase):
    """Context for the classify step (typed input + classifier chain + object store + cache)."""

    @property
    def input(self) -> IngestStageEnrichStepClassifyInput:
        """The step's typed input."""
        return self._input

    @property
    def classifier_chain(self) -> "Chain[Any, Any]":
        """The ordered figure classifier chain (built per-collection at assembly)."""
        return self.service("classifier_chain")

    @property
    def object_store(self) -> S3Client:
        """The SeaweedFS S3 client the figure crops are downloaded from."""
        return self.service("object_store")

    @property
    def provider_cache(self) -> ProviderCallCache:
        """The cross-document provider-call cache (keyed on the crop sha256)."""
        return self.service("provider_cache")


__all__ = ["IngestStageEnrichStepClassifyContext"]

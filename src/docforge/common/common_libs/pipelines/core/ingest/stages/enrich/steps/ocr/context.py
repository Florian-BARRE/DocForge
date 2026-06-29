# ====== Code Summary ======
# The OCR step's context - narrows ``input`` and exposes the two services it requires: the OCR chain
# (the ordered OCR providers) and the cross-document provider-call cache.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from common_libs.pipelines.capabilities.caches import ProviderCallCache
from common_libs.pipelines.capabilities.chain import Chain

# ====== Local Project Imports ======
from ..base import IngestStageEnrichStepContextBase
from .io import IngestStageEnrichStepOcrInput


class IngestStageEnrichStepOcrContext(IngestStageEnrichStepContextBase):
    """Context for the OCR step (typed input + OCR chain + provider cache)."""

    @property
    def input(self) -> IngestStageEnrichStepOcrInput:
        """The step's typed input."""
        return self._input

    @property
    def ocr_chain(self) -> "Chain[Any, Any]":
        """The ordered OCR chain (empty when OCR is disabled for the collection)."""
        return self.service("ocr_chain")

    @property
    def provider_cache(self) -> ProviderCallCache:
        """The cross-document provider-call cache (keyed on the crop sha256 + language)."""
        return self.service("provider_cache")


__all__ = ["IngestStageEnrichStepOcrContext"]

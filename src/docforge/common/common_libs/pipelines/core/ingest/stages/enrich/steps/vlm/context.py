# ====== Code Summary ======
# The VLM step's context - narrows ``input`` and exposes the two services it requires: the VLM chain
# (the ordered vision-language providers) and the cross-document provider-call cache.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from common_libs.pipelines.capabilities.caches import ProviderCallCache
from common_libs.pipelines.capabilities.chain import Chain

# ====== Local Project Imports ======
from ..base import IngestStageEnrichStepContextBase
from .io import IngestStageEnrichStepVlmInput


class IngestStageEnrichStepVlmContext(IngestStageEnrichStepContextBase):
    """Context for the VLM step (typed input + VLM chain + provider cache)."""

    @property
    def input(self) -> IngestStageEnrichStepVlmInput:
        """The step's typed input."""
        return self._input

    @property
    def vlm_chain(self) -> "Chain[Any, Any]":
        """The ordered VLM chain (empty when VLM is disabled for the collection)."""
        return self.service("vlm_chain")

    @property
    def provider_cache(self) -> ProviderCallCache:
        """The cross-document provider-call cache (keyed on the crop sha256 + grounding/schema)."""
        return self.service("provider_cache")


__all__ = ["IngestStageEnrichStepVlmContext"]

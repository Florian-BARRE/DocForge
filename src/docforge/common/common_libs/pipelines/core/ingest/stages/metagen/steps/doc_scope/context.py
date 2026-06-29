# ====== Code Summary ======
# The document-scope step's context — narrows ``input`` to this step's typed input and exposes the LLM
# chain and the provider-call cache it requires as typed accessors (``ctx.llm_chain`` /
# ``ctx.provider_cache``). Both are infrastructure injected as services — not abstracted behind a port.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from common_libs.pipelines.bricks.caches import ProviderCallCache
from common_libs.pipelines.bricks.chain import Chain

# ====== Local Project Imports ======
from ..base import IngestStageMetagenStepContextBase
from .io import IngestStageMetagenStepDocScopeInput


class IngestStageMetagenStepDocScopeContext(IngestStageMetagenStepContextBase):
    """Context for the document-scope step (typed input + the LLM chain + the provider cache)."""

    @property
    def input(self) -> IngestStageMetagenStepDocScopeInput:
        """The step's typed input."""
        return self._input

    @property
    def llm_chain(self) -> Chain[Any, Any]:
        """The injected LLM provider chain."""
        return self.service("llm_chain")

    @property
    def provider_cache(self) -> ProviderCallCache:
        """The cross-document provider-call cache."""
        return self.service("provider_cache")


__all__ = ["IngestStageMetagenStepDocScopeContext"]

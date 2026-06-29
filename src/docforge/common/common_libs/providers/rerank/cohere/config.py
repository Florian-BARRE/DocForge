# ====== Code Summary ======
# Pydantic config for the Cohere Rerank external cloud API provider.
# Registered via @register("rerank") so the provider auto-discovers on import.
# build() instantiates CohereRerankProvider; availability() reports key presence.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from common_libs.config.pipeline._registry import register
from common_libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common_libs.pipeline.bricks.providers.rerank.cohere.provider import CohereRerankProvider


@register("rerank")
class CohereRerankConfig(BaseModel):
    """
    Configuration for the Cohere Rerank cloud API.

    Config id: "cohere_rerank" — Cohere rerank-v3.5 or later; api_key REQUIRED.
    Cloud-only (no local server needed).

    Attributes:
        id: Provider discriminator — always "cohere_rerank".
        api_key: Cohere API key — REQUIRED, build() raises if empty after merge.
        model: Cohere rerank model (default ``rerank-v3.5``).
    """

    _label: ClassVar[str] = "Cohere Rerank — cloud cross-encoder (api_key required)"
    _category: ClassVar[str] = "rerank"

    id: Literal["cohere_rerank"] = "cohere_rerank"
    api_key: str = Field(default="", description="Cohere API key — REQUIRED.")
    model: str = Field(default="rerank-v3.5", description="Cohere rerank model.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Flatten legacy {id, params:{}} DB shape to a flat dict before validation."""
        return _flatten_provider_spec(v)

    def build(self) -> CohereRerankProvider:
        """
        Instantiate CohereRerankProvider from this configuration.

        Raises:
            ValueError: When api_key is empty — Cohere always requires authentication.

        Returns:
            CohereRerankProvider: A configured Cohere reranking provider instance.
        """
        if not self.api_key:
            raise ValueError(
                "CohereRerankConfig.build(): api_key is required for the Cohere Rerank API."
            )
        from common_libs.pipeline.bricks.providers.rerank.cohere.provider import CohereRerankProvider  # lazy runtime brick (L3)
        return CohereRerankProvider(api_key=self.api_key, model=self.model)

    def merge_defaults(self, cfg: Any) -> CohereRerankConfig:
        """
        Return this config unchanged — api_key is per-collection.

        Args:
            cfg: Unused — kept for call-site signature compatibility.

        Returns:
            CohereRerankConfig: This config, unchanged.
        """
        _ = cfg
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Report as usable — the Cohere API key is supplied per-collection."""
        _ = cfg
        return True, "Cohere rerank · API key per-collection"


__all__ = ["CohereRerankConfig"]

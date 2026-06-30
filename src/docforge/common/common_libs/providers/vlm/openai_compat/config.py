# ====== Code Summary ======
# Config for the unified OpenAI-compatible VLM provider (local OR external).
# Registered under id="openai_compat"; a `locality` flag replaces the former two classes
# (LocalVlmConfig id="openai_compat" + OpenAIVlmConfig id="openai"). The legacy id "openai"
# is still accepted and mapped to locality="external" for backward compatibility.

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
    from common_libs.providers.vlm.openai_compat.provider import OpenAICompatVlmProvider


@register("vlm")
class OpenAICompatVlmConfig(BaseModel):
    """
    Configuration for an OpenAI-compatible vision model — local or external.

    Config id: ``"openai_compat"``. The ``locality`` flag selects the deployment:
      - ``"local"`` — self-hosted (vLLM/Ollama/LM Studio); api_key optional; base_url required.
      - ``"external"`` — cloud (OpenAI/Mistral/OpenRouter); api_key required.

    """

    _label: ClassVar[str] = "OpenAI-compatible VLM — local or external (locality flag)"
    _category: ClassVar[str] = "vlm"

    id: Literal["openai_compat"] = "openai_compat"
    locality: Literal["local", "external"] = Field(
        default="local", description="'local' (self-hosted) or 'external' (cloud, api_key required)."
    )
    base_url: str = Field(
        default="", description="Server URL (per-collection) — required, no implicit cloud default."
    )
    model: str = Field(default="", description="Vision model identifier.")
    api_key: str = Field(default="", description="Bearer token; required for external, optional for local.")
    timeout_s: int = Field(default=0, ge=0, le=600, description="HTTP timeout in seconds (0 = locality default).")
    max_tokens: int = Field(default=1024, ge=64, le=8192, description="Max generated tokens.")

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, v: Any) -> Any:
        """Flatten the nested ``{id, params}`` spec shape to a flat dict before validation."""
        return _flatten_provider_spec(v)

    def build(self) -> OpenAICompatVlmProvider:
        """Instantiate the provider; base_url + model are required, external requires api_key."""
        # base_url is ALWAYS per-collection — no implicit cloud default (never silently point an
        # "openai_compat" VLM at api.openai.com).
        if not self.base_url:
            raise ValueError(
                "OpenAICompatVlmConfig.build(): base_url is required (per-collection) — "
                "no implicit cloud default."
            )
        if not self.model:
            raise ValueError("OpenAICompatVlmConfig.build(): model is required.")
        if self.locality == "external" and not self.api_key:
            raise ValueError("OpenAICompatVlmConfig.build(): api_key is required for locality='external'.")
        from common_libs.providers.vlm.openai_compat.provider import OpenAICompatVlmProvider  # lazy runtime brick (L3)
        return OpenAICompatVlmProvider(
            api_base_url=self.base_url,
            model=self.model,
            locality=self.locality,
            api_key=self.api_key,
            timeout_s=self.timeout_s or None,
            max_tokens=self.max_tokens,
        )

    def merge_defaults(self, cfg: Any) -> OpenAICompatVlmConfig:
        """
        Return this config unchanged — base_url/model/api_key are per-collection.

        Args:
            cfg: Unused — kept for call-site signature compatibility.

        Returns:
            OpenAICompatVlmConfig: This config, unchanged.
        """
        _ = cfg
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Report as usable — base_url + model + key are supplied per-collection."""
        _ = cfg
        return True, "VLM (OpenAI-compatible) · base_url + model + key per-collection"


__all__ = ["OpenAICompatVlmConfig"]

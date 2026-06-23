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
from libs.config.pipeline._registry import register
from libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .provider import OpenAICompatVlmProvider

_DEFAULT_EXTERNAL_BASE_URL = "https://api.openai.com/v1"


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
    base_url: str = Field(default="", description="Server URL (empty external → OpenAI default).")
    model: str = Field(default="", description="Vision model identifier.")
    api_key: str = Field(default="", description="Bearer token; required for external, optional for local.")
    timeout_s: int = Field(default=0, ge=0, le=600, description="HTTP timeout in seconds (0 = locality default).")
    max_tokens: int = Field(default=1024, ge=64, le=8192, description="Max generated tokens.")
    cost_per_call: float = Field(default=0.0, ge=0.0, description="Estimated USD per call (0 for local).")

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, v: Any) -> Any:
        """Flatten the nested ``{id, params}`` spec shape to a flat dict before validation."""
        return _flatten_provider_spec(v)

    def build(self) -> OpenAICompatVlmProvider:
        """Instantiate the provider; local requires base_url, external requires api_key."""
        if not self.base_url and self.locality == "local":
            raise ValueError("OpenAICompatVlmConfig.build(): base_url is required for locality='local'.")
        if not self.model:
            raise ValueError("OpenAICompatVlmConfig.build(): model is required.")
        if self.locality == "external" and not self.api_key:
            raise ValueError("OpenAICompatVlmConfig.build(): api_key is required for locality='external'.")
        return OpenAICompatVlmProvider(
            api_base_url=self.base_url or _DEFAULT_EXTERNAL_BASE_URL,
            model=self.model,
            locality=self.locality,
            api_key=self.api_key,
            timeout_s=self.timeout_s or None,
            max_tokens=self.max_tokens,
            cost_per_call=self.cost_per_call,
        )

    def merge_defaults(self, cfg: Any) -> OpenAICompatVlmConfig:
        """Fill missing fields from VLM_* env defaults (shared by both localities)."""
        return self.model_copy(update={
            "base_url": self.base_url or getattr(cfg, "VLM_API_BASE_URL", self.base_url),
            "model": self.model or getattr(cfg, "VLM_MODEL", self.model),
            "api_key": self.api_key or getattr(cfg, "VLM_API_KEY", ""),
            "timeout_s": self.timeout_s or getattr(cfg, "VLM_TIMEOUT_S", self.timeout_s),
            "max_tokens": getattr(cfg, "VLM_MAX_TOKENS", self.max_tokens),
            "cost_per_call": getattr(cfg, "VLM_COST_PER_CALL", self.cost_per_call),
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Report availability — local on base_url+model, external on api_key+model."""
        base_url = getattr(cfg, "VLM_API_BASE_URL", "")
        model = getattr(cfg, "VLM_MODEL", "")
        api_key = getattr(cfg, "VLM_API_KEY", "")
        if base_url and model:
            return True, f"Local · {model} @ {base_url}"
        if api_key and api_key != "local" and model:
            return True, f"Cloud API · {model}"
        return True, "Set base_url+model (local) or api_key+model (external) to enable"


__all__ = ["OpenAICompatVlmConfig"]

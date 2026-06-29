# ====== Code Summary ======
# Config for the unified OpenAI-compatible LLM provider (local OR external).
# Registered under id="openai_compat"; a `locality` flag replaces the former two classes
# (id="local_llm" + id="openai_llm"). Both legacy ids are still accepted and mapped to the
# matching locality for backward compatibility.

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
    from common_libs.providers.llm.openai_compat.provider import OpenAICompatLLMProvider

_DEFAULT_EXTERNAL_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_LOCAL_BASE_URL = "http://localhost:8080/v1"


@register("llm")
class OpenAICompatLLMConfig(BaseModel):
    """
    Configuration for an OpenAI-compatible chat LLM — local or external.

    Config id: ``"openai_compat"``. The ``locality`` flag selects the deployment:
      - ``"external"`` — cloud OpenAI; ``api_key`` required (from the collection config).
      - ``"local"`` — self-hosted (vLLM/Ollama/llama.cpp); ``api_key`` usually ``"local"``.
    """

    _label: ClassVar[str] = "OpenAI-compatible LLM — local or external (locality flag)"
    _category: ClassVar[str] = "llm"

    id: Literal["openai_compat"] = "openai_compat"
    locality: Literal["local", "external"] = Field(
        default="local", description="'local' (self-hosted) or 'external' (cloud OpenAI, api_key required)."
    )
    base_url: str = Field(default="", description="Chat server URL (empty external → OpenAI default).")
    api_key: str = Field(default="local", description="Bearer token; required for external, 'local' for self-hosted.")
    model: str = Field(default="gpt-4o-mini", description="Model identifier.")
    max_tokens: int = Field(default=512, ge=1, description="Default maximum tokens to generate.")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature.")

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, v: Any) -> Any:
        """Flatten the nested ``{id, params}`` spec shape to a flat dict before validation."""
        return _flatten_provider_spec(v)

    def build(self) -> OpenAICompatLLMProvider:
        """Instantiate the provider; external requires api_key."""
        if self.locality == "external" and (not self.api_key or self.api_key == "local"):
            raise ValueError("OpenAICompatLLMConfig.build(): api_key is required for locality='external'.")
        base_url = self.base_url or (_DEFAULT_EXTERNAL_BASE_URL if self.locality == "external" else _DEFAULT_LOCAL_BASE_URL)
        from common_libs.providers.llm.openai_compat.provider import OpenAICompatLLMProvider  # lazy runtime brick (L3)
        return OpenAICompatLLMProvider(
            base_url=base_url,
            locality=self.locality,
            api_key=self.api_key,
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

    def merge_defaults(self, cfg: Any) -> OpenAICompatLLMConfig:
        """
        Return this config unchanged — base_url/api_key/model are per-collection.

        Args:
            cfg: Unused — kept for call-site signature compatibility.

        Returns:
            OpenAICompatLLMConfig: This config, unchanged.
        """
        _ = cfg
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Report as usable — base_url + key are supplied by the collection config."""
        _ = cfg
        return True, "OpenAI-compatible LLM · base_url + key per-collection"


__all__ = ["OpenAICompatLLMConfig"]

# ====== Code Summary ======
# Configuration class for the locally-hosted OpenAI-compatible VLM server provider.
# Registered under id "openai_compat" — covers vLLM, Ollama, LM Studio, and any
# self-hosted server implementing the OpenAI chat-completions vision API.

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from libs.config.pipeline._registry import register
from libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .openai_compat import LocalOpenAICompatVlmProvider


@register("vlm")
class LocalVlmConfig(BaseModel):
    """
    Configuration for a locally-hosted OpenAI-compatible VLM server.

    Config id: "openai_compat" — vLLM, Ollama, LM Studio, no auth required.

    Attributes:
        base_url: Server URL (e.g. http://vllm:8001/v1).
        model: Model identifier (e.g. Qwen/Qwen2.5-VL-7B-Instruct).
        api_key: Optional bearer token (empty = no Authorization header).
        timeout_s: HTTP timeout in seconds (default 30 s — local network).
        max_tokens: Maximum generated tokens per response.
        cost_per_call: Always 0.0 for local providers.
    """

    _label: ClassVar[str] = "Local VLM — OpenAI-compat server (vLLM / Ollama / LM Studio)"
    _category: ClassVar[str] = "vlm"

    id: Literal["openai_compat"] = "openai_compat"
    base_url: str = Field(default="", description="Local server URL (e.g. http://vllm:8001/v1).")
    model: str = Field(default="", description="Model identifier.")
    api_key: str = Field(default="", description="Optional bearer token.")
    timeout_s: int = Field(default=30, ge=5, le=300, description="HTTP timeout in seconds.")
    max_tokens: int = Field(default=1024, ge=64, le=8192, description="Max generated tokens.")
    cost_per_call: float = Field(default=0.0, ge=0.0, description="USD per call (0 for local).")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        return _flatten_provider_spec(v)

    def build(self) -> LocalOpenAICompatVlmProvider:
        """Instantiate LocalOpenAICompatVlmProvider — raises ValueError when base_url empty."""
        if not self.base_url:
            raise ValueError(
                "LocalVlmConfig.build(): base_url is required. "
                "Call merge_defaults(cfg) first or supply the URL explicitly."
            )
        if not self.model:
            raise ValueError("LocalVlmConfig.build(): model is required.")
        return LocalOpenAICompatVlmProvider(
            api_base_url=self.base_url,
            model=self.model,
            api_key=self.api_key,
            timeout_s=self.timeout_s,
            max_tokens=self.max_tokens,
            cost_per_call=self.cost_per_call,
        )

    def merge_defaults(self, cfg: Any) -> LocalVlmConfig:
        """Return a copy of this config with missing fields filled from runtime cfg."""
        return self.model_copy(update={
            "base_url": self.base_url or getattr(cfg, "VLM_API_BASE_URL", ""),
            "model": self.model or getattr(cfg, "VLM_MODEL", ""),
            "api_key": self.api_key or getattr(cfg, "VLM_API_KEY", ""),
            "timeout_s": getattr(cfg, "VLM_TIMEOUT_S", self.timeout_s),
            "max_tokens": getattr(cfg, "VLM_MAX_TOKENS", self.max_tokens),
            "cost_per_call": getattr(cfg, "VLM_COST_PER_CALL", self.cost_per_call),
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Available when a base_url is configured (no api_key required)."""
        base_url = getattr(cfg, "VLM_API_BASE_URL", "")
        model = getattr(cfg, "VLM_MODEL", "")
        if base_url and model:
            return True, f"Local · {model} @ {base_url}"
        return True, "Set base_url + model to enable (local vLLM, Ollama, or any OpenAI-compat server)"

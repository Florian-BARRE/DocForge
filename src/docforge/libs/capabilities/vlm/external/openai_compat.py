# ====== Code Summary ======
# External OpenAI-compatible VLM provider — for cloud APIs (OpenAI, Mistral, OpenRouter).
# API key is mandatory. Config id: "openai"

from __future__ import annotations

from libs.capabilities.vlm._openai_compat_base import _OpenAICompatVlmBase
from typing import Any, ClassVar, Literal
from pydantic import BaseModel, Field, model_validator
from libs.core.contracts._registry import register


class OpenAIVlmProvider(_OpenAICompatVlmBase):
    """
    VLM provider for external OpenAI-compatible cloud APIs.

    Compatible with: OpenAI (GPT-4o, GPT-4-vision), Mistral vision,
    Gemini-compat endpoints, OpenRouter, and any cloud API that implements
    the OpenAI chat-completions shape with vision support.

    An api_key is REQUIRED — the constructor raises ValueError when empty
    so misconfiguration is caught at job start, not silently at inference time.

    Config id: "openai"

    Attributes:
        name (str): "openai-vlm"
        version (str): Derived from the model name (last path segment).
        runs_on (str): "remote"
    """

    name: str = "openai-vlm"
    runs_on: str = "remote"

    def __init__(
        self,
        api_base_url: str,
        api_key: str,
        model: str,
        timeout_s: int = 120,
        max_tokens: int = 1024,
        cost_per_call: float = 0.0,
    ) -> None:
        """
        Initialize the external OpenAI-compatible VLM provider.

        Args:
            api_base_url (str): Cloud API base URL (e.g. https://api.openai.com/v1).
            api_key (str): Bearer token — REQUIRED, raises ValueError if empty.
            model (str): Model identifier (e.g. gpt-4o, mistral-vision-latest).
            timeout_s (int): HTTP timeout in seconds (default 120 s — cloud latency).
            max_tokens (int): Max generated tokens per response.
            cost_per_call (float): Estimated USD per call for budget tracking.

        Raises:
            ValueError: When api_key is empty — cloud APIs always require auth.
        """
        if not api_key:
            raise ValueError(
                "OpenAIVlmProvider requires an api_key. "
                "For local servers without auth, use LocalOpenAICompatVlmProvider instead."
            )
        self._init_openai_compat_vlm(
            api_base_url=api_base_url,
            api_key=api_key,
            model=model,
            timeout_s=timeout_s,
            max_tokens=max_tokens,
            cost_per_call=cost_per_call,
        )
        self.logger.debug(
            f"OpenAIVlmProvider: model={model!r} url={self._api_base_url}"
        )


# ─── Config ──────────────────────────────────────────────────────────────────



def _flatten_provider_spec(v: Any) -> Any:
    if isinstance(v, dict) and "params" in v and isinstance(v.get("params"), dict):
        return {"id": v.get("id"), **v["params"]}
    return v


@register("vlm")
class OpenAIVlmConfig(BaseModel):
    """
    Configuration for an external OpenAI-compatible VLM cloud API.

    Config id: "openai" — OpenAI, Mistral, OpenRouter; api_key REQUIRED.

    Attributes:
        base_url: Cloud API base URL (e.g. https://api.openai.com/v1).
        api_key: Bearer token — REQUIRED, build() raises if empty after merge.
        model: Model identifier (e.g. gpt-4o, mistral-vision-latest).
        timeout_s: HTTP timeout in seconds (default 120 s — cloud latency).
        max_tokens: Maximum generated tokens per response.
        cost_per_call: Estimated USD per call for budget tracking.
    """

    _label: ClassVar[str] = "Cloud VLM — OpenAI / Mistral / OpenRouter (api_key required)"
    _category: ClassVar[str] = "vlm"

    id: Literal["openai"] = "openai"
    base_url: str = Field(default="https://api.openai.com/v1", description="Cloud API base URL.")
    api_key: str = Field(default="", description="Bearer token — REQUIRED.")
    model: str = Field(default="gpt-4o", description="Vision model identifier.")
    timeout_s: int = Field(default=120, ge=5, le=600, description="HTTP timeout in seconds.")
    max_tokens: int = Field(default=1024, ge=64, le=8192, description="Max generated tokens.")
    cost_per_call: float = Field(default=0.001, ge=0.0, description="Estimated USD per call.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        return _flatten_provider_spec(v)

    def build(self) -> "OpenAIVlmProvider":
        """Instantiate OpenAIVlmProvider — raises ValueError when api_key is empty."""
        if not self.api_key:
            raise ValueError(
                "OpenAIVlmConfig.build(): api_key is required for external cloud APIs. "
                "Call merge_defaults(cfg) first or supply the key explicitly."
            )
        return OpenAIVlmProvider(
            api_base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            timeout_s=self.timeout_s,
            max_tokens=self.max_tokens,
            cost_per_call=self.cost_per_call,
        )

    def merge_defaults(self, cfg: Any) -> "OpenAIVlmConfig":
        return self.model_copy(update={
            "base_url": self.base_url or getattr(cfg, "VLM_API_BASE_URL", self.base_url),
            "api_key": self.api_key or getattr(cfg, "VLM_API_KEY", ""),
            "model": self.model or getattr(cfg, "VLM_MODEL", self.model),
            "timeout_s": getattr(cfg, "VLM_TIMEOUT_S", self.timeout_s),
            "max_tokens": getattr(cfg, "VLM_MAX_TOKENS", self.max_tokens),
            "cost_per_call": getattr(cfg, "VLM_COST_PER_CALL", self.cost_per_call),
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Available when an API key is configured. Always selectable (key can be set on the fly)."""
        api_key = getattr(cfg, "VLM_API_KEY", "")
        model = getattr(cfg, "VLM_MODEL", "")
        if api_key and api_key != "local":
            return True, f"Cloud API · {model}"
        return True, "Set api_key + model to enable (OpenAI, Mistral, OpenRouter)"

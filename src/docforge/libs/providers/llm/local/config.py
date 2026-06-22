# ====== Code Summary ======
# Pydantic config for the local OpenAI-compatible LLM provider.
# Registered via @register("llm") so the provider auto-discovers on import.
# build() instantiates LocalLLMProvider; availability() checks server reachability.

# ====== Standard Library Imports ======
from __future__ import annotations

import socket
from typing import Any, ClassVar, Literal
from urllib.parse import urlparse

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from libs.config.pipeline._registry import register
from libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .openai_compat import LocalLLMProvider


@register("llm")
class LocalLLMConfig(BaseModel):
    """
    Configuration for a local OpenAI-compatible LLM server.

    Config id: "local_llm" — targets vLLM, Ollama, llama.cpp, or any
    OpenAI-compatible chat completions endpoint accessible within the network.

    Attributes:
        id: Provider discriminator — always "local_llm".
        base_url: LLM server base URL (e.g. ``http://localhost:8080/v1``).
        api_key: Authentication key (typically ``"local"`` for self-hosted servers).
        model: Model identifier passed to the completions request.
        max_tokens: Default maximum tokens to generate per call.
        temperature: Default sampling temperature (0.0 = deterministic).
    """

    _label: ClassVar[str] = "Local LLM — OpenAI-compatible server (vLLM / Ollama / llama.cpp)"
    _category: ClassVar[str] = "llm"

    id: Literal["local_llm"] = "local_llm"
    base_url: str = Field(default="http://localhost:8080/v1", description="LLM server base URL.")
    api_key: str = Field(default="local", description="API key (use 'local' for unauthenticated servers).")
    model: str = Field(default="Qwen/Qwen2.5-7B-Instruct", description="Model identifier.")
    max_tokens: int = Field(default=512, ge=1, description="Default maximum tokens to generate.")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Flatten legacy {id, params:{}} DB shape to a flat dict before validation."""
        return _flatten_provider_spec(v)

    def build(self) -> LocalLLMProvider:
        """
        Instantiate LocalLLMProvider from this config.

        Returns:
            LocalLLMProvider: Ready-to-use local LLM provider instance.
        """
        return LocalLLMProvider(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

    def merge_defaults(self, cfg: Any) -> LocalLLMConfig:
        """
        Merge deployment env defaults into this config.

        Args:
            cfg: RUNTIME_CONFIG instance providing LLM_API_BASE_URL / LLM_API_KEY / LLM_MODEL.

        Returns:
            LocalLLMConfig: Updated config with env defaults applied where fields have defaults.
        """
        return self.model_copy(update={
            "base_url": self.base_url or getattr(cfg, "LLM_API_BASE_URL", self.base_url),
            "api_key": self.api_key or getattr(cfg, "LLM_API_KEY", self.api_key),
            "model": self.model or getattr(cfg, "LLM_MODEL", self.model),
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """
        Check whether the local LLM server is reachable.

        Args:
            cfg: RUNTIME_CONFIG instance providing LLM_API_BASE_URL.

        Returns:
            tuple[bool, str]: (is_available, human-readable description).
        """
        base_url = getattr(cfg, "LLM_API_BASE_URL", "http://localhost:8080/v1")
        try:
            p = urlparse(base_url)
            host, port = p.hostname or "localhost", p.port or 8080
            with socket.create_connection((host, port), timeout=1):
                return True, f"Local LLM · OpenAI-compat · {base_url}"
        except OSError:
            return False, f"Local LLM server not reachable at {base_url}"


__all__ = ["LocalLLMConfig"]

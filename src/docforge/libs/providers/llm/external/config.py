# ====== Code Summary ======
# Pydantic config for the OpenAI cloud LLM provider.
# Registered via @register("llm") so the provider auto-discovers on import.
# build() instantiates OpenAILLMProvider; availability() reports key presence.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from libs.config.pipeline._registry import register
from libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .openai import OpenAILLMProvider


@register("llm")
class OpenAILLMConfig(BaseModel):
    """
    Configuration for the OpenAI cloud chat completions API.

    Config id: "openai_llm" — public OpenAI API; api_key REQUIRED.
    Connects to https://api.openai.com/v1/chat/completions.

    Attributes:
        id: Provider discriminator — always "openai_llm".
        base_url: OpenAI base URL (always https://api.openai.com/v1 — not configurable).
        api_key: OpenAI API key — REQUIRED, build() raises if empty after merge.
        model: OpenAI model (default ``gpt-4o-mini``).
        max_tokens: Default maximum tokens to generate.
        temperature: Default sampling temperature.
    """

    _label: ClassVar[str] = "OpenAI LLM — cloud chat completions (api_key required)"
    _category: ClassVar[str] = "llm"

    id: Literal["openai_llm"] = "openai_llm"
    base_url: str = Field(default="https://api.openai.com/v1", description="OpenAI base URL.")
    api_key: str = Field(default="", description="OpenAI API key — REQUIRED.")
    model: str = Field(default="gpt-4o-mini", description="OpenAI model identifier.")
    max_tokens: int = Field(default=512, ge=1, description="Default maximum tokens to generate.")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Flatten legacy {id, params:{}} DB shape to a flat dict before validation."""
        return _flatten_provider_spec(v)

    def build(self) -> OpenAILLMProvider:
        """
        Instantiate OpenAILLMProvider from this configuration.

        Raises:
            ValueError: When api_key is empty — OpenAI always requires authentication.

        Returns:
            OpenAILLMProvider: A configured OpenAI LLM provider instance.
        """
        if not self.api_key:
            raise ValueError(
                "OpenAILLMConfig.build(): api_key is required for the OpenAI API."
            )
        return OpenAILLMProvider(
            api_key=self.api_key,
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

    def merge_defaults(self, cfg: Any) -> OpenAILLMConfig:
        """
        Merge deployment-level defaults into this config.

        Fills ``api_key`` from ``cfg.OPENAI_API_KEY`` or ``cfg.LLM_API_KEY``
        when the field is empty.

        Args:
            cfg: Runtime config object exposing env-level defaults.

        Returns:
            OpenAILLMConfig: Updated config copy with merged defaults.
        """
        return self.model_copy(update={
            "api_key": self.api_key or getattr(cfg, "OPENAI_API_KEY", "") or getattr(cfg, "LLM_API_KEY", ""),
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """
        Report availability based on whether OPENAI_API_KEY or LLM_API_KEY is set.

        Args:
            cfg: Runtime config object for env-level key inspection.

        Returns:
            tuple[bool, str]: (always True, human-readable description).
        """
        api_key = getattr(cfg, "OPENAI_API_KEY", "") or getattr(cfg, "LLM_API_KEY", "")
        if api_key:
            return True, "OpenAI LLM · cloud chat completions · key configured"
        return True, "Set OPENAI_API_KEY to enable OpenAI LLM"


__all__ = ["OpenAILLMConfig"]

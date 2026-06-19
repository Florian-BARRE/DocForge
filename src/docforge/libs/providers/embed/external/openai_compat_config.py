# ====== Code Summary ======
# Configuration class for the external OpenAI-compatible embedding cloud API.
# Registered under id="openai" — targets OpenAI, Azure, Mistral, Cohere, etc.
# Separated from the provider so auto_import() discovers it via walk_packages.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from libs.core.contracts._registry import register
from libs.core.contracts.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .openai_compat import OpenAIEmbedProvider


@register("embed")
class OpenAIEmbedConfig(BaseModel):
    """
    Configuration for an external OpenAI-compatible embedding cloud API.

    Config id: "openai" — OpenAI, Azure, Mistral, Cohere; api_key REQUIRED.
    Dense-only (no sparse vectors).

    Attributes:
        base_url (str): Cloud API base URL (e.g. https://api.openai.com/v1).
        api_key (str): Bearer token — REQUIRED, build() raises if empty after merge.
        model (str): Embedding model (default text-embedding-3-large, 3072-dim).
        batch_size (int): Max texts per batch.
        dimension (int): Vector dimension override (0 = auto from known model names).
    """

    _label: ClassVar[str] = "Cloud embed — OpenAI / Azure / Mistral (api_key required, dense only)"
    _category: ClassVar[str] = "embed"

    id: Literal["openai"] = "openai"
    base_url: str = Field(default="https://api.openai.com/v1", description="Cloud API base URL.")
    api_key: str = Field(default="", description="Bearer token — REQUIRED.")
    model: str = Field(default="text-embedding-3-large", description="Embedding model.")
    batch_size: int = Field(default=32, ge=1, le=256, description="Max texts per batch.")
    dimension: int = Field(default=0, ge=0, description="Vector dimension (0 = auto).")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Flatten legacy ``{id, params}`` provider spec into a flat dict."""
        return _flatten_provider_spec(v)

    def build(self) -> OpenAIEmbedProvider:
        """
        Instantiate OpenAIEmbedProvider from this configuration.

        Raises:
            ValueError: When api_key is empty — external cloud APIs always require auth.

        Returns:
            OpenAIEmbedProvider: A configured external embedding provider instance.
        """
        if not self.api_key:
            raise ValueError(
                "OpenAIEmbedConfig.build(): api_key is required for external cloud APIs."
            )
        return OpenAIEmbedProvider(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            batch_size=self.batch_size,
            dimension=self.dimension,
        )

    def merge_defaults(self, cfg: Any) -> OpenAIEmbedConfig:
        """
        Merge deployment-level defaults into this config.

        Fills ``api_key`` from ``cfg.OPENAI_API_KEY`` or ``cfg.EMBED_API_KEY``
        when the field is empty.

        Args:
            cfg: Runtime config object exposing env-level defaults.

        Returns:
            OpenAIEmbedConfig: Updated config copy with merged defaults.
        """
        return self.model_copy(update={
            "api_key": self.api_key or getattr(cfg, "OPENAI_API_KEY", "") or getattr(cfg, "EMBED_API_KEY", ""),
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """
        Report availability of this provider in the current deployment environment.

        Args:
            cfg: Runtime config object for env-level key inspection.

        Returns:
            tuple[bool, str]: Always ``True`` (cloud API), with a status message.
        """
        api_key = getattr(cfg, "OPENAI_API_KEY", "") or getattr(cfg, "EMBED_API_KEY", "")
        if api_key:
            return True, "Cloud API · dense only"
        return True, "Set api_key to enable (OpenAI, Azure, Mistral, Cohere)"

# ====== Code Summary ======
# Configuration class for a locally-hosted OpenAI-compatible embedding server.
# Registered under id="openai_compat" — targets vLLM, Ollama, LM Studio, etc.
# Separated from the provider so auto_import() discovers it via walk_packages.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from libs.config.pipeline._registry import register
from libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .openai_compat import LocalOpenAICompatEmbedProvider


@register("embed")
class LocalOpenAIEmbedConfig(BaseModel):
    """
    Configuration for a locally-hosted OpenAI-compatible embedding server.

    Config id: "openai_compat" — vLLM, Ollama, LM Studio; no auth required.
    Dense-only (no sparse vectors).

    Attributes:
        base_url (str): Server URL (e.g. http://vllm:8000/v1).
        model (str): Model identifier.
        api_key (str): Optional bearer token.
        batch_size (int): Max texts per batch.
        dimension (int): Vector dimension override (0 = auto from known model names).
    """

    _label: ClassVar[str] = "Local embed — OpenAI-compat server (vLLM / Ollama, dense only)"
    _category: ClassVar[str] = "embed"

    id: Literal["openai_compat"] = "openai_compat"
    base_url: str = Field(default="", description="Local server URL.")
    model: str = Field(default="text-embedding-3-large", description="Embedding model.")
    api_key: str = Field(default="", description="Optional bearer token.")
    batch_size: int = Field(default=32, ge=1, le=256, description="Max texts per batch.")
    dimension: int = Field(default=0, ge=0, description="Vector dimension (0 = auto).")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Flatten legacy ``{id, params}`` provider spec into a flat dict."""
        return _flatten_provider_spec(v)

    def build(self) -> LocalOpenAICompatEmbedProvider:
        """
        Instantiate LocalOpenAICompatEmbedProvider from this configuration.

        Raises:
            ValueError: When base_url is empty.

        Returns:
            LocalOpenAICompatEmbedProvider: A configured local embedding provider instance.
        """
        if not self.base_url:
            raise ValueError("LocalOpenAIEmbedConfig.build(): base_url is required.")
        return LocalOpenAICompatEmbedProvider(
            base_url=self.base_url,
            model=self.model,
            api_key=self.api_key,
            batch_size=self.batch_size,
            dimension=self.dimension,
        )

    def merge_defaults(self, cfg: Any) -> LocalOpenAIEmbedConfig:
        """
        Merge deployment-level defaults into this config.

        No env-level defaults apply for local servers — the caller sets ``base_url``
        explicitly in the collection config.

        Args:
            cfg: Runtime config object (unused for this provider).

        Returns:
            LocalOpenAIEmbedConfig: This config unchanged.
        """
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """
        Report availability of this provider in the current deployment environment.

        Args:
            cfg: Runtime config object (unused for this provider).

        Returns:
            tuple[bool, str]: Always ``True`` with a status hint.
        """
        return True, "Dense only · set base_url + model to enable"

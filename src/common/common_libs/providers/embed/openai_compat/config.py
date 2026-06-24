# ====== Code Summary ======
# Config for the unified OpenAI-compatible embedding provider (local OR external).
# Registered under id="openai_compat"; a `locality` flag ("local"|"external") selects the
# deployment, replacing the former two classes (external + local).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from common_libs.config.pipeline._registry import register
from common_libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .provider import OpenAICompatEmbedProvider

# Default cloud endpoint used when an external config omits base_url.
_DEFAULT_EXTERNAL_BASE_URL = "https://api.openai.com/v1"


@register("embed")
class OpenAICompatEmbedConfig(BaseModel):
    """
    Configuration for an OpenAI-compatible embedding server — local or external.

    Config id: ``"openai_compat"``. The ``locality`` flag selects the deployment:
      - ``"external"`` — cloud API (OpenAI/Azure/Mistral); ``api_key`` required (from config
        or the OPENAI_API_KEY / EMBED_API_KEY env via merge_defaults).
      - ``"local"`` — self-hosted (vLLM/Ollama/…); ``api_key`` optional, ``base_url`` required.

    Dense-only. Pair with a separate sparse source (EmbedConfig.sparse) for hybrid search.
    """

    _label: ClassVar[str] = "OpenAI-compatible embed — local or external (locality flag, dense only)"
    _category: ClassVar[str] = "embed"

    id: Literal["openai_compat"] = "openai_compat"
    locality: Literal["local", "external"] = Field(
        default="local", description="'local' (self-hosted, api_key optional) or 'external' (cloud, api_key required)."
    )
    base_url: str = Field(default="", description="Server URL (empty external → OpenAI default).")
    api_key: str = Field(default="", description="Bearer token — required when locality='external'.")
    model: str = Field(default="text-embedding-3-large", description="Embedding model.")
    batch_size: int = Field(default=32, ge=1, le=256, description="Max texts per batch.")
    dimension: int = Field(default=0, ge=0, description="Vector dimension (0 = auto).")

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, v: Any) -> Any:
        """Flatten the nested ``{id, params}`` spec shape to a flat dict before validation."""
        return _flatten_provider_spec(v)

    def build(self) -> OpenAICompatEmbedProvider:
        """
        Instantiate the provider; require api_key for external, base_url for local.

        Raises:
            ValueError: When external without api_key, or local without base_url.

        Returns:
            OpenAICompatEmbedProvider: Configured provider.
        """
        base_url = self.base_url or (_DEFAULT_EXTERNAL_BASE_URL if self.locality == "external" else "")
        if self.locality == "external" and not self.api_key:
            raise ValueError("OpenAICompatEmbedConfig.build(): api_key is required for locality='external'.")
        if self.locality == "local" and not base_url:
            raise ValueError("OpenAICompatEmbedConfig.build(): base_url is required for locality='local'.")
        return OpenAICompatEmbedProvider(
            base_url=base_url,
            locality=self.locality,
            api_key=self.api_key,
            model=self.model,
            batch_size=self.batch_size,
            dimension=self.dimension,
        )

    def merge_defaults(self, cfg: Any) -> OpenAICompatEmbedConfig:
        """
        Fill external defaults from the deployment env (api_key + the cloud base_url).

        Local configs are returned unchanged (the caller sets base_url explicitly).

        Args:
            cfg: Runtime config exposing OPENAI_API_KEY / EMBED_API_KEY.

        Returns:
            OpenAICompatEmbedConfig: Config copy with external defaults merged.
        """
        if self.locality != "external":
            return self
        return self.model_copy(update={
            "api_key": self.api_key or getattr(cfg, "OPENAI_API_KEY", "") or getattr(cfg, "EMBED_API_KEY", ""),
            "base_url": self.base_url or _DEFAULT_EXTERNAL_BASE_URL,
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Report availability — cloud always reachable; local needs an explicit base_url."""
        api_key = getattr(cfg, "OPENAI_API_KEY", "") or getattr(cfg, "EMBED_API_KEY", "")
        hint = "Cloud (external): set api_key. Local: set base_url + model. Dense only."
        return True, (hint if not api_key else f"Cloud key detected · {hint}")

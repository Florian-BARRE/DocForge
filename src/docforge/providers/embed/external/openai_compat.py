# ====== Code Summary ======
# External OpenAI-compatible embedding provider — for cloud APIs (OpenAI, Azure, Mistral, …).
# API key is mandatory. Dense-only (OpenAI protocol has no sparse endpoint).

# ====== Standard Library Imports ======
from __future__ import annotations
from typing import Any, ClassVar, Literal
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from providers._registry import register
from providers.embed._openai_compat_base import _OpenAICompatBase


class OpenAIEmbedProvider(_OpenAICompatBase):
    """
    Embedding provider for external OpenAI-compatible cloud APIs.

    Targets any cloud endpoint that implements the OpenAI ``/embeddings`` API and
    requires bearer token authentication: OpenAI, Azure OpenAI, Mistral, Cohere,
    Together AI, etc.

    An ``api_key`` is **required** — the constructor raises ``ValueError`` when it
    is empty so misconfiguration is caught at job start, not silently at inference time.

    Config id: ``"openai"``

    Attributes:
        name (str): ``"openai"``
        version (str): ``"text-embedding-3-large"`` (default model name).
        runs_on (str): ``"remote"``
    """

    name: str = "openai"
    version: str = "text-embedding-3-large"
    runs_on: str = "remote"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "",
        timeout_s: int = 60,
        batch_size: int = 32,
        dimension: int = 0,
    ) -> None:
        """
        Initialise the external OpenAI-compatible embedding provider.

        Args:
            base_url (str): API base URL (e.g. ``https://api.openai.com/v1``).
            api_key (str): Bearer token — **required**, raises if empty.
            model (str): Model name sent in the request body. Defaults to ``version``.
            timeout_s (int): HTTP timeout in seconds.  Default is 60 s (network latency).
            batch_size (int): Maximum texts per batch request.
            dimension (int): Vector dimension override (0 = auto from known model names).

        Raises:
            ValueError: When ``api_key`` is empty — external APIs always require auth.
        """
        if not api_key:
            raise ValueError(
                f"OpenAIEmbedProvider requires an api_key. "
                f"For local servers without auth, use LocalOpenAICompatEmbedProvider instead."
            )
        self._init_openai_compat(
            base_url=base_url,
            api_key=api_key,
            model=model or self.version,
            timeout_s=timeout_s,
            batch_size=batch_size,
            dimension=dimension,
        )
        self.logger.debug(
            f"OpenAIEmbedProvider: "
            f"model={self._model} dim={self._dimension} url={self._base_url}"
        )


# ─── Config ──────────────────────────────────────────────────────────────────



def _flatten_provider_spec(v: Any) -> Any:
    if isinstance(v, dict) and "params" in v and isinstance(v.get("params"), dict):
        return {"id": v.get("id"), **v["params"]}
    return v


@register("embed")
class OpenAIEmbedConfig(BaseModel):
    """
    Configuration for an external OpenAI-compatible embedding cloud API.

    Config id: "openai" — OpenAI, Azure, Mistral, Cohere; api_key REQUIRED.
    Dense-only (no sparse vectors).

    Attributes:
        base_url: Cloud API base URL (e.g. https://api.openai.com/v1).
        api_key: Bearer token — REQUIRED, build() raises if empty after merge.
        model: Embedding model (default text-embedding-3-large, 3072-dim).
        batch_size: Max texts per batch.
        dimension: Vector dimension override (0 = auto from known model names).
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
        return _flatten_provider_spec(v)

    def build(self) -> "OpenAIEmbedProvider":
        """Instantiate OpenAIEmbedProvider — raises ValueError when api_key empty."""
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

    def merge_defaults(self, cfg: Any) -> "OpenAIEmbedConfig":
        return self.model_copy(update={
            "api_key": self.api_key or getattr(cfg, "OPENAI_API_KEY", "") or getattr(cfg, "EMBED_API_KEY", ""),
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        api_key = getattr(cfg, "OPENAI_API_KEY", "") or getattr(cfg, "EMBED_API_KEY", "")
        if api_key:
            return True, "Cloud API · dense only"
        return True, "Set api_key to enable (OpenAI, Azure, Mistral, Cohere)"

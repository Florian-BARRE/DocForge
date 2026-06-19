# ====== Code Summary ======
# Local OpenAI-compatible embedding provider — for self-hosted servers (vLLM, Ollama, LM Studio).
# No API key required. Dense-only (OpenAI protocol has no sparse endpoint).

# ====== Standard Library Imports ======
from __future__ import annotations
from typing import Any, ClassVar, Literal
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from libs.core.contracts._registry import register
from libs.core.contracts.spec_utils import flatten_provider_spec as _flatten_provider_spec
from libs.capabilities.embed._openai_compat_base import _OpenAICompatBase


class LocalOpenAICompatEmbedProvider(_OpenAICompatBase):
    """
    Embedding provider for a locally-hosted OpenAI-compatible server.

    Designed for self-hosted inference servers that implement the OpenAI ``/embeddings``
    API without requiring authentication: vLLM, Ollama, LM Studio, FastEmbed-server, etc.

    No API key is required.  If your local server does require auth, pass ``api_key``
    explicitly; if it requires credentials you do not control, use ``OpenAIEmbedProvider``
    (``external/openai_compat.py``) instead.

    Config id: ``"openai_compat"``

    Attributes:
        name (str): ``"local-openai-compat"``
        version (str): ``"text-embedding-3-large"`` (default model name).
        runs_on (str): ``"local"``
    """

    name: str = "local-openai-compat"
    version: str = "text-embedding-3-large"
    runs_on: str = "local"

    def __init__(
        self,
        base_url: str,
        model: str = "",
        api_key: str = "",
        timeout_s: int = 30,
        batch_size: int = 32,
        dimension: int = 0,
    ) -> None:
        """
        Initialise the local OpenAI-compatible embedding provider.

        Args:
            base_url (str): Server URL (e.g. ``http://vllm:8000/v1``).
            model (str): Model name sent in the request body. Defaults to ``version``.
            api_key (str): Optional bearer token (empty = no ``Authorization`` header).
            timeout_s (int): HTTP timeout in seconds.  Default is 30 s (local network).
            batch_size (int): Maximum texts per batch request.
            dimension (int): Vector dimension override (0 = auto from known model names).
        """
        self._init_openai_compat(
            base_url=base_url,
            api_key=api_key,
            model=model or self.version,
            timeout_s=timeout_s,
            batch_size=batch_size,
            dimension=dimension,
        )
        self.logger.debug(
            f"LocalOpenAICompatEmbedProvider: "
            f"model={self._model} dim={self._dimension} url={self._base_url}"
        )


# ─── Config ──────────────────────────────────────────────────────────────────



@register("embed")
class LocalOpenAIEmbedConfig(BaseModel):
    """
    Configuration for a locally-hosted OpenAI-compatible embedding server.

    Config id: "openai_compat" — vLLM, Ollama, LM Studio; no auth required.
    Dense-only (no sparse vectors).

    Attributes:
        base_url: Server URL (e.g. http://vllm:8000/v1).
        model: Model identifier.
        api_key: Optional bearer token.
        batch_size: Max texts per batch.
        dimension: Vector dimension override (0 = auto from known model names).
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
        return _flatten_provider_spec(v)

    def build(self) -> "LocalOpenAICompatEmbedProvider":
        """Instantiate LocalOpenAICompatEmbedProvider from this config."""
        if not self.base_url:
            raise ValueError("LocalOpenAIEmbedConfig.build(): base_url is required.")
        return LocalOpenAICompatEmbedProvider(
            base_url=self.base_url,
            model=self.model,
            api_key=self.api_key,
            batch_size=self.batch_size,
            dimension=self.dimension,
        )

    def merge_defaults(self, cfg: Any) -> "LocalOpenAIEmbedConfig":
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        return True, "Dense only · set base_url + model to enable"

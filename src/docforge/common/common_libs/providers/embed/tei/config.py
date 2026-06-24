# ====== Code Summary ======
# Pydantic config for the TEI (Text Embeddings Inference) local embedding provider.
# Registered via @register("embed") so the provider auto-discovers on import.
# build() instantiates TeiEmbedProvider; availability() checks server reachability.

# ====== Standard Library Imports ======
from __future__ import annotations

import socket
from typing import Any, ClassVar, Literal
from urllib.parse import urlparse

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from common_libs.config.pipeline._registry import register
from common_libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .provider import TeiEmbedProvider


@register("embed")
class TeiEmbedConfig(BaseModel):
    """
    Configuration for the TEI (Text Embeddings Inference) local embedding server.

    Config id: "tei" — BGE-M3, 1024-dim dense + BM25 sparse, hybrid search.
    Requires a running TEI server (URL from the TEI_BASE_URL env, e.g. http://bge:80).

    Attributes:
        id: Provider discriminator — always "tei".
        locality: "local" (self-hosted TEI) or "external" (remote TEI endpoint). Editable —
            a TEI server can run either side; the flag drives the device gate.
        base_url: TEI server URL.
        api_key: Optional bearer token (a remote TEI endpoint may require it).
        model: Embedding model identifier (default BAAI/bge-m3).
        batch_size: Max texts per batch request.
        embed_sparse: Also produce BM25 sparse vectors (enables hybrid search).
    """

    _label: ClassVar[str] = "TEI (BGE-M3) — dense+sparse hybrid embedding (1024-dim, local or external)"
    _category: ClassVar[str] = "embed"

    id: Literal["tei"] = "tei"
    locality: Literal["local", "external"] = Field(
        default="local", description="'local' (self-hosted TEI) or 'external' (remote TEI endpoint)."
    )
    # Empty by default so merge_defaults sources the URL from TEI_BASE_URL (deployment
    # env) — a non-empty default would shadow the env and pin a possibly-wrong port.
    base_url: str = Field(default="", description="TEI server URL (defaults to TEI_BASE_URL env).")
    api_key: str = Field(default="", description="Optional bearer token (remote TEI endpoints may require it).")
    model: str = Field(default="BAAI/bge-m3", description="Embedding model served by TEI.")
    batch_size: int = Field(default=32, ge=1, le=256, description="Max texts per batch.")
    embed_sparse: bool = Field(default=True, description="Produce BM25 sparse vectors (hybrid search).")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Flatten legacy {id, params:{}} DB shape to a flat dict before validation."""
        return _flatten_provider_spec(v)

    def build(self) -> TeiEmbedProvider:
        """
        Instantiate TeiEmbedProvider from this config.

        Returns:
            TeiEmbedProvider: Ready-to-use provider instance.
        """
        return TeiEmbedProvider(
            base_url=self.base_url or "http://bge:80",
            model=self.model,
            locality=self.locality,
            api_key=self.api_key,
            batch_size=self.batch_size,
            embed_sparse=self.embed_sparse,
        )

    def merge_defaults(self, cfg: Any) -> TeiEmbedConfig:
        """
        Merge deployment env defaults into this config.

        Args:
            cfg: RUNTIME_CONFIG instance providing TEI_BASE_URL / TEI_BATCH_SIZE.

        Returns:
            TeiEmbedConfig: Updated config with env defaults applied where needed.
        """
        return self.model_copy(update={
            "base_url": self.base_url or getattr(cfg, "TEI_BASE_URL", "") or "http://bge:80",
            "api_key": self.api_key or getattr(cfg, "TEI_API_KEY", ""),
            "batch_size": self.batch_size or getattr(cfg, "TEI_BATCH_SIZE", self.batch_size),
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """
        Check whether the TEI server is reachable.

        Args:
            cfg: RUNTIME_CONFIG instance providing TEI_BASE_URL.

        Returns:
            tuple[bool, str]: (is_available, human-readable description).
        """
        base_url = getattr(cfg, "TEI_BASE_URL", "http://bge:80")
        try:
            p = urlparse(base_url)
            host, port = p.hostname or "tei", p.port or 8080
            with socket.create_connection((host, port), timeout=1):
                return True, f"BGE-M3 · 1024-dim · dense+sparse · {base_url}"
        except OSError:
            return False, f"TEI server not reachable at {base_url}"


__all__ = ["TeiEmbedConfig"]

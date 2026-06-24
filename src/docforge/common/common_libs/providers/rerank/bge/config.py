# ====== Code Summary ======
# Pydantic config for the BGE-Reranker-v2-m3 local reranking provider (TEI).
# Registered via @register("rerank") so the provider auto-discovers on import.
# build() instantiates BgeRerankProvider; availability() checks server reachability.

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
from .provider import BgeRerankProvider


@register("rerank")
class BgeRerankerConfig(BaseModel):
    """
    Configuration for the BGE-Reranker-v2-m3 local cross-encoder via TEI.

    Config id: "bge_reranker" — BAAI/bge-reranker-v2-m3, served by TEI on a
    separate container (reranker:80).  Requires a running TEI reranker server.

    Attributes:
        id: Provider discriminator — always "bge_reranker".
        locality: "local" (self-hosted TEI) or "external" (remote TEI endpoint). Editable.
        base_url: TEI reranker server URL (e.g. ``http://reranker:80``).
        api_key: Optional bearer token (a remote TEI endpoint may require it).
        batch_size: Maximum texts per HTTP request to TEI.
    """

    _label: ClassVar[str] = "BGE-Reranker-v2-m3 — cross-encoder reranker via TEI (local or external)"
    _category: ClassVar[str] = "rerank"

    id: Literal["bge_reranker"] = "bge_reranker"
    locality: Literal["local", "external"] = Field(
        default="local", description="'local' (self-hosted TEI) or 'external' (remote TEI endpoint)."
    )
    base_url: str = Field(default="http://reranker:80", description="TEI reranker server URL.")
    api_key: str = Field(default="", description="Optional bearer token (remote TEI endpoints may require it).")
    batch_size: int = Field(default=32, ge=1, le=256, description="Max texts per batch request.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Flatten legacy {id, params:{}} DB shape to a flat dict before validation."""
        return _flatten_provider_spec(v)

    def build(self) -> BgeRerankProvider:
        """
        Instantiate BgeRerankProvider from this config.

        Returns:
            BgeRerankProvider: Ready-to-use reranking provider instance.
        """
        return BgeRerankProvider(
            base_url=self.base_url,
            batch_size=self.batch_size,
            locality=self.locality,
            api_key=self.api_key,
        )

    def merge_defaults(self, cfg: Any) -> BgeRerankerConfig:
        """
        Merge deployment env defaults into this config.

        Args:
            cfg: RUNTIME_CONFIG instance providing BGE_RERANKER_URL / BGE_RERANKER_BATCH_SIZE.

        Returns:
            BgeRerankerConfig: Updated config with env defaults applied where fields are empty/zero.
        """
        return self.model_copy(update={
            "base_url": self.base_url or getattr(cfg, "BGE_RERANKER_URL", self.base_url),
            "api_key": self.api_key or getattr(cfg, "BGE_RERANKER_API_KEY", ""),
            "batch_size": self.batch_size or getattr(cfg, "BGE_RERANKER_BATCH_SIZE", self.batch_size),
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """
        Check whether the TEI reranker server is reachable.

        Args:
            cfg: RUNTIME_CONFIG instance providing BGE_RERANKER_URL.

        Returns:
            tuple[bool, str]: (is_available, human-readable description).
        """
        base_url = getattr(cfg, "BGE_RERANKER_URL", "http://reranker:80")
        try:
            p = urlparse(base_url)
            host, port = p.hostname or "reranker", p.port or 80
            with socket.create_connection((host, port), timeout=1):
                return True, f"BGE-Reranker-v2-m3 · cross-encoder · {base_url}"
        except OSError:
            return False, f"TEI reranker not reachable at {base_url}"


__all__ = ["BgeRerankerConfig"]

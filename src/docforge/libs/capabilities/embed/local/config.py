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
from libs.core.contracts._registry import register
from libs.core.contracts.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .tei import TeiEmbedProvider


@register("embed")
class TeiEmbedConfig(BaseModel):
    """
    Configuration for the TEI (Text Embeddings Inference) local embedding server.

    Config id: "tei" — BGE-M3, 1024-dim dense + BM25 sparse, hybrid search.
    Requires a running TEI server (e.g. http://tei:8080).

    Attributes:
        id: Provider discriminator — always "tei".
        base_url: TEI server URL.
        model: Embedding model identifier (default BAAI/bge-m3).
        batch_size: Max texts per batch request.
        embed_sparse: Also produce BM25 sparse vectors (enables hybrid search).
    """

    _label: ClassVar[str] = "TEI (BGE-M3) — local dense+sparse hybrid embedding (1024-dim)"
    _category: ClassVar[str] = "embed"

    id: Literal["tei"] = "tei"
    base_url: str = Field(default="http://tei:8080", description="TEI server URL.")
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
            base_url=self.base_url,
            model=self.model,
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
            "base_url": self.base_url or getattr(cfg, "TEI_BASE_URL", self.base_url),
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
        base_url = getattr(cfg, "TEI_BASE_URL", "http://tei:8080")
        try:
            p = urlparse(base_url)
            host, port = p.hostname or "tei", p.port or 8080
            with socket.create_connection((host, port), timeout=1):
                return True, f"BGE-M3 · 1024-dim · dense+sparse · {base_url}"
        except OSError:
            return False, f"TEI server not reachable at {base_url}"


__all__ = ["TeiEmbedConfig"]

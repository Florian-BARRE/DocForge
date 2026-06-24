# ====== Code Summary ======
# Pydantic config for the `bge_server` embedding provider — our LOCAL BGE model host
# (src/bge_server) serving BGE-M3 dense + native multilingual sparse on the TEI HTTP contract.
# Registered via @register("embed"). Unlike the off-the-shelf TEI image (abandoned: its ONNX
# backend crash-loops on BGE-M3), bge_server is reliable AND serves BGE-M3 sparse.
#
# Per the project rule, the URL + secret are PER-COLLECTION (from the stored pipeline config),
# NOT from RUNTIME_CONFIG — so merge_defaults does NOT read the deployment env.

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
# bge_server speaks the TEI HTTP contract → it reuses the TEI HTTP client provider.
from ..tei.provider import TeiEmbedProvider

# Canonical URL of the local bge service (compose service `bge_server`). A structural default
# (a service name, not a secret) — a collection may override it per-collection.
_DEFAULT_BGE_URL = "http://bge_server:80"


@register("embed")
class BgeServerEmbedConfig(BaseModel):
    """
    Configuration for the local `bge_server` embedding service (BGE-M3 dense + sparse).

    Config id: "bge_server". URL + key come from the COLLECTION config (per-collection),
    never from RUNTIME_CONFIG. base_url defaults to the local `bge_server` service.

    Attributes:
        id: Provider discriminator — always "bge_server".
        locality: "local" (self-hosted) or "external" (remote endpoint) — drives the device gate.
        base_url: bge_server URL (defaults to the local `bge_server` service).
        api_key: Optional bearer token (a remote/secured endpoint may require it).
        model: Embedding model identifier (default BAAI/bge-m3).
        batch_size: Max texts per batch request.
        embed_sparse: Also produce native multilingual sparse vectors (enables hybrid search).
    """

    _label: ClassVar[str] = "bge_server (BGE-M3) — dense+sparse hybrid embedding (1024-dim, local)"
    _category: ClassVar[str] = "embed"

    id: Literal["bge_server"] = "bge_server"
    locality: Literal["local", "external"] = Field(
        default="local", description="'local' (self-hosted bge) or 'external' (remote endpoint)."
    )
    base_url: str = Field(default=_DEFAULT_BGE_URL, description="bge_server URL (per-collection).")
    api_key: str = Field(default="", description="Optional bearer token (secured endpoints).")
    model: str = Field(default="BAAI/bge-m3", description="Embedding model served by bge_server.")
    batch_size: int = Field(default=32, ge=1, le=256, description="Max texts per batch.")
    embed_sparse: bool = Field(default=True, description="Produce native sparse vectors (hybrid search).")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Flatten legacy {id, params:{}} DB shape to a flat dict before validation."""
        return _flatten_provider_spec(v)

    def build(self) -> TeiEmbedProvider:
        """Instantiate the (TEI-protocol) HTTP embed provider pointed at bge_server."""
        return TeiEmbedProvider(
            base_url=self.base_url or _DEFAULT_BGE_URL,
            model=self.model,
            locality=self.locality,
            api_key=self.api_key,
            batch_size=self.batch_size,
            embed_sparse=self.embed_sparse,
        )

    def merge_defaults(self, cfg: Any) -> "BgeServerEmbedConfig":
        """
        No-op merge — per the project rule, bge_server's URL/key are PER-COLLECTION and never
        sourced from RUNTIME_CONFIG. ``cfg`` is accepted for interface parity and ignored.
        """
        _ = cfg
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Probe the default bge service URL (cfg ignored — no env-sourced provider config)."""
        _ = cfg
        try:
            p = urlparse(_DEFAULT_BGE_URL)
            with socket.create_connection((p.hostname or "bge_server", p.port or 80), timeout=1):
                return True, f"BGE-M3 · 1024-dim · dense+sparse · {_DEFAULT_BGE_URL}"
        except OSError:
            return False, f"bge_server not reachable at {_DEFAULT_BGE_URL}"


__all__ = ["BgeServerEmbedConfig"]

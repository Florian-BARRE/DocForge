# ====== Code Summary ======
# Pydantic config for the `bge_server` reranking provider — the SAME local BGE model host
# (src/bge_server) that serves dense+sparse embedding also serves BGE-reranker-v2-m3 on its
# /rerank endpoint. Registered via @register("rerank"). URL/key are PER-COLLECTION (never env);
# base_url defaults to the local bge service and merge_defaults reads NOTHING from RUNTIME_CONFIG.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from common_libs.config.pipeline._registry import register
from common_libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
# bge_server speaks the TEI /rerank contract → it reuses the same HTTP client provider.
if TYPE_CHECKING:
    from common_libs.providers.rerank.bge.provider import BgeRerankProvider


@register("rerank")
class BgeServerRerankConfig(BaseModel):
    """
    Configuration for the local `bge_server` reranker (BGE-reranker-v2-m3).

    Config id: "bge_server". URL + key come from the COLLECTION config (per-collection),
    never from RUNTIME_CONFIG. base_url defaults to the local `bge_server` service.

    Attributes:
        id: Provider discriminator — always "bge_server".
        locality: "local" (self-hosted) or "external" (remote endpoint) — drives the device gate.
        base_url: bge_server URL (defaults to the local `bge_server` service).
        api_key: Optional bearer token (a remote/secured endpoint may require it).
        batch_size: Maximum texts per HTTP request.
    """

    _label: ClassVar[str] = "bge_server (BGE-reranker-v2-m3) — cross-encoder reranker (local)"
    _category: ClassVar[str] = "rerank"

    id: Literal["bge_server"] = "bge_server"
    locality: Literal["local", "external"] = Field(
        default="local", description="'local' (self-hosted bge) or 'external' (remote endpoint)."
    )
    base_url: str = Field(
        default="http://bge_server:80",
        description="bge_server URL — defaults to the local compose service, overridable per-collection.",
    )
    api_key: str = Field(default="", description="Optional bearer token (secured endpoints).")
    batch_size: int = Field(default=32, ge=1, le=256, description="Max texts per batch request.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Flatten legacy {id, params:{}} DB shape to a flat dict before validation."""
        return _flatten_provider_spec(v)

    def build(self) -> BgeRerankProvider:
        """Instantiate the (TEI-protocol) HTTP rerank provider pointed at bge_server."""
        from common_libs.providers.rerank.bge.provider import BgeRerankProvider  # lazy runtime brick (L3)
        return BgeRerankProvider(
            base_url=self.base_url,
            batch_size=self.batch_size,
            locality=self.locality,
            api_key=self.api_key,
        )

    def merge_defaults(self, cfg: Any) -> "BgeServerRerankConfig":
        """No-op merge — URL/key are per-collection, never sourced from RUNTIME_CONFIG."""
        _ = cfg
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Static capability description (no network probe — reachability is /monitoring's concern)."""
        _ = cfg
        return True, "BGE-reranker-v2-m3 · cross-encoder (local bge_server)"


__all__ = ["BgeServerRerankConfig"]

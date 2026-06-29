# ====== Code Summary ======
# Pydantic config for the legacy BGE-Reranker-v2-m3 reranking provider (off-the-shelf TEI).
#
# DEPRECATED as a CHOICE: the off-the-shelf TEI reranker image was replaced by the local
# `bge_server` model host (which serves BGE-reranker-v2-m3 on the same TEI /rerank contract).
# This config is therefore NO LONGER registered via @register("rerank") — it does not appear in
# discovery / the rerank discriminated union, and `bge_server` is the canonical rerank provider.
#
# The class is KEPT (unregistered) only so existing stored pipelines with `id == "bge_reranker"`
# can be referenced during backward-compat normalization; RerankConfig rewrites such specs to
# "bge_server" BEFORE the discriminated-union dispatch, so a BgeRerankerConfig instance is never
# produced. The HTTP client (BgeRerankProvider, in provider.py) stays the shared rerank client
# used by BgeServerRerankConfig.build().

# ====== Standard Library Imports ======
from __future__ import annotations

import socket
from typing import Any, ClassVar, Literal
from urllib.parse import urlparse

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from common_libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common_libs.providers.rerank.bge.provider import BgeRerankProvider


class BgeRerankerConfig(BaseModel):
    """
    Legacy configuration for the BGE-Reranker-v2-m3 cross-encoder via off-the-shelf TEI.

    DEPRECATED CHOICE — not registered in the "rerank" category. Kept only for reference;
    stored configs with id="bge_reranker" are normalized to "bge_server" before validation.

    Config id: "bge_reranker" — BAAI/bge-reranker-v2-m3, served by TEI on a
    separate container (reranker:80).  Requires a running TEI reranker server.

    Attributes:
        id: Provider discriminator — always "bge_reranker".
        locality: "local" (self-hosted TEI) or "external" (remote TEI endpoint). Editable.
        base_url: TEI reranker server URL (e.g. ``http://bge_server:80``).
        api_key: Optional bearer token (a remote TEI endpoint may require it).
        batch_size: Maximum texts per HTTP request to TEI.
    """

    _label: ClassVar[str] = "BGE-Reranker-v2-m3 — cross-encoder reranker via TEI (local or external)"
    _category: ClassVar[str] = "rerank"

    id: Literal["bge_reranker"] = "bge_reranker"
    locality: Literal["local", "external"] = Field(
        default="local", description="'local' (self-hosted TEI) or 'external' (remote TEI endpoint)."
    )
    base_url: str = Field(default="http://bge_server:80", description="TEI reranker server URL.")
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
        from common_libs.providers.rerank.bge.provider import BgeRerankProvider  # lazy runtime brick (L3)
        return BgeRerankProvider(
            base_url=self.base_url,
            batch_size=self.batch_size,
            locality=self.locality,
            api_key=self.api_key,
        )

    def merge_defaults(self, cfg: Any) -> BgeRerankerConfig:
        """
        Return this config unchanged — all defaults are per-collection.

        The Pydantic field defaults already provide the structural defaults at
        construction time; nothing is sourced from the deployment env.

        Args:
            cfg: Unused — kept for call-site signature compatibility.

        Returns:
            BgeRerankerConfig: This config, unchanged.
        """
        _ = cfg
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """
        Probe the structural-default bge server for reachability.

        Args:
            cfg: Unused — the per-collection base_url is not visible here.

        Returns:
            tuple[bool, str]: (is_available, human-readable description).
        """
        _ = cfg
        base_url = "http://bge_server:80"
        try:
            p = urlparse(base_url)
            host, port = p.hostname or "bge_server", p.port or 80
            with socket.create_connection((host, port), timeout=1):
                return True, "BGE reranker · http://bge_server:80"
        except OSError:
            return False, "bge reranker not reachable at http://bge_server:80"


__all__ = ["BgeRerankerConfig"]

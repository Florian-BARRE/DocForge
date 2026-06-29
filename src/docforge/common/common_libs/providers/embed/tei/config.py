# ====== Code Summary ======
# Pydantic config for the legacy TEI (Text Embeddings Inference) embedding provider.
#
# DEPRECATED as a CHOICE: the off-the-shelf TEI image was replaced by the local `bge_server`
# model host (which speaks the same TEI HTTP contract). This config is therefore NO LONGER
# registered via @register("embed") — it does not appear in discovery / the discriminated union,
# and an empty embed chain now defaults to `bge_server` (see EmbedConfig / build_default_pipeline).
#
# The class is KEPT (unregistered) only so existing stored pipelines with `id == "tei"` can be
# referenced during backward-compat normalization; EmbedConfig rewrites such specs to "bge_server"
# BEFORE the discriminated-union dispatch, so a TeiEmbedConfig instance is never produced.
# The HTTP client runtime (TeiEmbedProvider) now lives in the pipeline brick
# common_libs.pipeline.bricks.providers.embed and is the shared embed client used by
# BgeServerEmbedConfig.build() (lazy-imported there).

# ====== Standard Library Imports ======
from __future__ import annotations

import socket
from typing import TYPE_CHECKING, Any, ClassVar, Literal
from urllib.parse import urlparse

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from common_libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

if TYPE_CHECKING:
    # Type-only import of the runtime brick (L3); build() lazy-imports it at runtime so this
    # config-layer module has no module-level upward import into the pipeline.
    from common_libs.pipeline.bricks.providers.embed import TeiEmbedProvider


class TeiEmbedConfig(BaseModel):
    """
    Legacy configuration for the TEI (Text Embeddings Inference) embedding server.

    DEPRECATED CHOICE — not registered in the "embed" category. Kept only for reference;
    stored configs with id="tei" are normalized to "bge_server" before validation.

    Config id: "tei" — BGE-M3, 1024-dim dense + BM25 sparse, hybrid search.
    Requires a running TEI server (URL from the collection config (defaults to http://bge_server:80)).

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
    # Structural default points at the in-cluster bge_server service; per-collection configs
    # override it. No env sourcing — the URL lives in the collection config only.
    base_url: str = Field(default="http://bge_server:80", description="TEI server URL.")
    api_key: str = Field(default="", description="Optional bearer token (remote TEI endpoints may require it).")
    model: str = Field(default="BAAI/bge-m3", description="Embedding model served by TEI.")
    batch_size: int = Field(default=32, ge=1, le=256, description="Max texts per batch.")
    embed_sparse: bool = Field(default=True, description="Produce BM25 sparse vectors (hybrid search).")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Flatten legacy {id, params:{}} DB shape to a flat dict before validation."""
        return _flatten_provider_spec(v)

    def build(self) -> "TeiEmbedProvider":
        """
        Instantiate TeiEmbedProvider from this config.

        Lazy-imports the runtime brick (L3) so this config-layer module has no module-level
        upward import into the pipeline.

        Returns:
            TeiEmbedProvider: Ready-to-use provider instance.
        """
        # 1. Lazy import the runtime — function-local to keep the import graph acyclic.
        from common_libs.pipeline.bricks.providers.embed import TeiEmbedProvider

        return TeiEmbedProvider(
            base_url=self.base_url or "http://bge_server:80",
            model=self.model,
            locality=self.locality,
            api_key=self.api_key,
            batch_size=self.batch_size,
            embed_sparse=self.embed_sparse,
        )

    def merge_defaults(self, cfg: Any) -> TeiEmbedConfig:
        """
        Return this config unchanged — all defaults are per-collection.

        The Pydantic field defaults already provide the structural defaults at
        construction time; nothing is sourced from the deployment env.

        Args:
            cfg: Unused — kept for call-site signature compatibility.

        Returns:
            TeiEmbedConfig: This config, unchanged.
        """
        _ = cfg
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """
        Probe the structural-default bge_server server for reachability.

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
                return True, f"BGE-M3 · 1024-dim · dense+sparse · {base_url}"
        except OSError:
            return False, f"TEI/bge server not reachable at {base_url}"


__all__ = ["TeiEmbedConfig"]

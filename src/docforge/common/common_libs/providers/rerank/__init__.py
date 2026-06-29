# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all rerank providers (one folder per provider; bge = TEI cross-encoder
# with an editable locality flag, cohere = cloud API fixed external).
# ─────────────────────────────────────────────────────────────────────────────

import importlib

from common_libs.config.pipeline._registry import auto_import

auto_import(__name__)

# ─────────────────── Base ─────────────────────────────────────────── #
from .base import RerankProvider

# ─────────────────── Providers (one folder each) ───────────────────── #
# `bge_reranker` is no longer a registered rerank CHOICE (bge_server replaced the off-the-shelf TEI
# reranker image). The HTTP client BgeRerankProvider stays exported (lazily, below) — it is the
# shared rerank client reused by BgeServerRerankConfig.build(). BgeRerankerConfig is exported only
# for backward-compat reference; being unregistered, it is absent from the rerank discriminated union.
from .bge import BgeRerankerConfig
from .bge_server import BgeServerRerankConfig
from .cohere import CohereRerankConfig

# ─────────────────── Runtime re-exports (lazy) ─────────────────────── #
# Runtime providers are re-exported lazily (PEP 562) so importing this package for config
# auto-discovery never eagerly pulls a runtime HTTP client into the import graph. Each name is
# imported only when first accessed (typically inside the matching Config.build()), preserving the
# config/runtime layering.
_RUNTIME_EXPORTS = {
    "BgeRerankProvider": (".bge.provider", "BgeRerankProvider"),
    "CohereRerankProvider": (".cohere.provider", "CohereRerankProvider"),
}


def __getattr__(name: str):
    """Lazily import and return a runtime provider re-exported by this package."""
    target = _RUNTIME_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(target[0], __name__)
    return getattr(module, target[1])


# ─────────────────── Public API ───────────────────────────────────── #
__all__ = [
    "BgeRerankProvider",
    "BgeRerankerConfig",
    "BgeServerRerankConfig",
    "CohereRerankConfig",
    "CohereRerankProvider",
    "RerankProvider",
]

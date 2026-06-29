# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all parser backends and build the discriminated union.
# ─────────────────────────────────────────────────────────────────────────────

import importlib

from common_libs.config.pipeline._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import ParserProvider

# ------------------- Providers (one folder each) ------------------- #
from .docling import DoclingConfig

# ------------------- Discriminated Union ------------------- #
ParserConfig = build_union(get_configs("parser"))

# ------------------- Runtime re-exports (lazy) ------------------- #
# The runtime backend is re-exported lazily (PEP 562) so importing this package for config
# auto-discovery never eagerly pulls the heavy parser dependency (docling) into the lightweight
# app image. It is imported only when first accessed (typically inside DoclingConfig.build()),
# preserving the config/runtime layering.
_RUNTIME_EXPORTS = {
    "DoclingBackend": (".docling.core", "DoclingBackend"),
}


def __getattr__(name: str):
    """Lazily import and return a runtime backend re-exported by this package."""
    target = _RUNTIME_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(target[0], __name__)
    return getattr(module, target[1])


# ------------------- Public API ------------------- #
__all__ = [
    "DoclingBackend",
    "DoclingConfig",
    "ParserConfig",
    "ParserProvider",
]

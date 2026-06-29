# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all embedding providers and build the discriminated union.
# One folder per provider; local vs external is a `locality` flag on the config,
# not a separate class (openai_compat unifies the former local + external classes).
# ─────────────────────────────────────────────────────────────────────────────

import importlib

from common_libs.config.pipeline._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import EmbedProvider

# ------------------- Providers (one folder each) ------------------- #
from .bge_server import BgeServerEmbedConfig
from .openai_compat import OpenAICompatEmbedConfig

# `tei` is no longer a registered embed CHOICE (bge_server replaced the off-the-shelf TEI image).
# The runtime TeiEmbedProvider lives in common_libs.providers.embed.tei.provider; only the
# (unregistered, backward-compat) TeiEmbedConfig is exported here — it is absent from the
# EmbedProviderConfig discriminated union below.
from .tei import TeiEmbedConfig

# ------------------- Discriminated Union ------------------- #
EmbedProviderConfig = build_union(get_configs("embed"))

# ------------------- Runtime re-exports (lazy) ------------------- #
# Runtime providers are re-exported lazily (PEP 562) so importing this package for config
# auto-discovery never eagerly pulls a runtime HTTP client into the import graph. Each name is
# imported only when first accessed (e.g. inside TeiEmbedConfig.build() / BgeServerEmbedConfig.build()
# which resolve `TeiEmbedProvider` from this package), preserving the config/runtime layering.
_RUNTIME_EXPORTS = {
    "TeiEmbedProvider": (".tei.provider", "TeiEmbedProvider"),
    "OpenAICompatEmbedProvider": (".openai_compat.provider", "OpenAICompatEmbedProvider"),
    "CompositeEmbedProvider": (".composite", "CompositeEmbedProvider"),
}


def __getattr__(name: str):
    """Lazily import and return a runtime provider re-exported by this package."""
    target = _RUNTIME_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(target[0], __name__)
    return getattr(module, target[1])


# ------------------- Public API ------------------- #
__all__ = [
    "BgeServerEmbedConfig",
    "CompositeEmbedProvider",
    "EmbedProvider",
    "EmbedProviderConfig",
    "OpenAICompatEmbedConfig",
    "OpenAICompatEmbedProvider",
    "TeiEmbedConfig",
    "TeiEmbedProvider",
]

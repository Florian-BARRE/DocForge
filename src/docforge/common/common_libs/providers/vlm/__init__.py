# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all VLM providers and build the discriminated union.
# One folder per provider; local vs external is a `locality` flag on the unified
# openai_compat config, not a separate class.
# ─────────────────────────────────────────────────────────────────────────────

import importlib

from common_libs.config.pipeline._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import VlmProvider

# ------------------- Providers (one folder each) ------------------- #
from .openai_compat import OpenAICompatVlmConfig

# ------------------- Discriminated Union ------------------- #
VlmProviderConfig = build_union(get_configs("vlm"))

# ------------------- Runtime re-exports (lazy) ------------------- #
# Runtime providers are re-exported lazily (PEP 562) so importing this package for config
# auto-discovery never eagerly pulls a runtime HTTP client into the import graph. Each name is
# imported only when first accessed (typically inside OpenAICompatVlmConfig.build()), preserving
# the config/runtime layering.
_RUNTIME_EXPORTS = {
    "OpenAICompatVlmProvider": (".openai_compat.provider", "OpenAICompatVlmProvider"),
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
    "OpenAICompatVlmConfig",
    "OpenAICompatVlmProvider",
    "VlmProvider",
    "VlmProviderConfig",
]

# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all LLM providers (one folder per provider; local vs external is a
# `locality` flag on the unified openai_compat config, not a separate class).
# ─────────────────────────────────────────────────────────────────────────────

import importlib

from common_libs.config.pipeline._registry import auto_import

auto_import(__name__)

# ─────────────────── Base ─────────────────────────────────────────── #
from .base import LLMProvider

# ─────────────────── Providers (one folder each) ───────────────────── #
from .openai_compat import OpenAICompatLLMConfig

# ─────────────────── Runtime re-exports (lazy) ─────────────────────── #
# Runtime providers are re-exported lazily (PEP 562) so importing this package for config
# auto-discovery never eagerly pulls a runtime HTTP client into the import graph. Each name is
# imported only when first accessed (typically inside OpenAICompatLLMConfig.build()), preserving
# the config/runtime layering.
_RUNTIME_EXPORTS = {
    "OpenAICompatLLMProvider": (".openai_compat.provider", "OpenAICompatLLMProvider"),
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
    "LLMProvider",
    "OpenAICompatLLMConfig",
    "OpenAICompatLLMProvider",
]

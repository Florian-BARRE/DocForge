# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all VLM providers and build the discriminated union.
# One folder per provider; local vs external is a `locality` flag on the unified
# openai_compat config, not a separate class.
# ─────────────────────────────────────────────────────────────────────────────

from libs.config.pipeline._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import VlmProvider

# ------------------- Providers (one folder each) ------------------- #
from .openai_compat import OpenAICompatVlmConfig, OpenAICompatVlmProvider

# ------------------- Discriminated Union ------------------- #
VlmProviderConfig = build_union(get_configs("vlm"))

# ------------------- Public API ------------------- #
__all__ = [
    "OpenAICompatVlmConfig",
    "OpenAICompatVlmProvider",
    "VlmProvider",
    "VlmProviderConfig",
]

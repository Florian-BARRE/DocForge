# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all VLM providers and build the discriminated union.
# ─────────────────────────────────────────────────────────────────────────────

from providers._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import VlmProvider

# ------------------- Local Providers ------------------- #
from .local.openai_compat import LocalOpenAICompatVlmProvider, LocalVlmConfig

# ------------------- External Providers ------------------- #
from .external.openai_compat import OpenAIVlmConfig, OpenAIVlmProvider

# ------------------- Discriminated Union ------------------- #
VlmProviderConfig = build_union(get_configs("vlm"))

# ------------------- Backward Compatibility ------------------- #
OpenAICompatVlmProvider = LocalOpenAICompatVlmProvider

# ------------------- Public API ------------------- #
__all__ = [
    "LocalOpenAICompatVlmProvider",
    "LocalVlmConfig",
    "OpenAICompatVlmProvider",
    "OpenAIVlmConfig",
    "OpenAIVlmProvider",
    "VlmProvider",
    "VlmProviderConfig",
]

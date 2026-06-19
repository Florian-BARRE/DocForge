# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all VLM providers and build the discriminated union.
# ─────────────────────────────────────────────────────────────────────────────

from libs.config.pipeline._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import VlmProvider

# ------------------- External Providers ------------------- #
from .external.openai_compat import OpenAIVlmProvider
from .external.openai_compat_config import OpenAIVlmConfig

# ------------------- Local Providers ------------------- #
from .local.openai_compat import LocalOpenAICompatVlmProvider
from .local.openai_compat_config import LocalVlmConfig

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

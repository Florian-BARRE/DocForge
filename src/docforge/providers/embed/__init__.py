# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all embedding providers and build the discriminated union.
# ─────────────────────────────────────────────────────────────────────────────

from providers._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import EmbedProvider

# ------------------- Local Providers ------------------- #
from .local.tei import TeiEmbedConfig, TeiEmbedProvider
from .local.openai_compat import LocalOpenAIEmbedConfig, LocalOpenAICompatEmbedProvider

# ------------------- External Providers ------------------- #
from .external.openai_compat import OpenAIEmbedConfig, OpenAIEmbedProvider

# ------------------- Discriminated Union ------------------- #
EmbedProviderConfig = build_union(get_configs("embed"))

# ------------------- Public API ------------------- #
__all__ = [
    "EmbedProvider",
    "EmbedProviderConfig",
    "LocalOpenAICompatEmbedProvider",
    "LocalOpenAIEmbedConfig",
    "OpenAIEmbedConfig",
    "OpenAIEmbedProvider",
    "TeiEmbedConfig",
    "TeiEmbedProvider",
]

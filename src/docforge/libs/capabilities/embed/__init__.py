# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all embedding providers and build the discriminated union.
# ─────────────────────────────────────────────────────────────────────────────

from libs.core.contracts._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import EmbedProvider

# ------------------- External Providers ------------------- #
from .external.openai_compat import OpenAIEmbedConfig, OpenAIEmbedProvider
from .local.config import TeiEmbedConfig
from .local.openai_compat import LocalOpenAICompatEmbedProvider, LocalOpenAIEmbedConfig

# ------------------- Local Providers ------------------- #
from .local.tei import TeiEmbedProvider

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

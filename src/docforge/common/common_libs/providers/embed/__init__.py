# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all embedding providers and build the discriminated union.
# One folder per provider; local vs external is a `locality` flag on the config,
# not a separate class (openai_compat unifies the former local + external classes).
# ─────────────────────────────────────────────────────────────────────────────

from common_libs.config.pipeline._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import EmbedProvider
from .composite import CompositeEmbedProvider

# ------------------- Providers (one folder each) ------------------- #
from .bge_server import BgeServerEmbedConfig
from .openai_compat import OpenAICompatEmbedConfig, OpenAICompatEmbedProvider
from .tei import TeiEmbedConfig, TeiEmbedProvider

# ------------------- Discriminated Union ------------------- #
EmbedProviderConfig = build_union(get_configs("embed"))

# ------------------- Public API ------------------- #
__all__ = [
    "EmbedProvider",
    "CompositeEmbedProvider",
    "EmbedProviderConfig",
    "BgeServerEmbedConfig",
    "OpenAICompatEmbedConfig",
    "OpenAICompatEmbedProvider",
    "TeiEmbedConfig",
    "TeiEmbedProvider",
]

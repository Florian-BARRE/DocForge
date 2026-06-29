# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all embedding providers and build the discriminated union.
# One folder per provider; local vs external is a `locality` flag on the config,
# not a separate class (openai_compat unifies the former local + external classes).
# ─────────────────────────────────────────────────────────────────────────────

from common_libs.config.pipeline._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import EmbedProvider

# ------------------- Providers (one folder each) ------------------- #
from .bge_server import BgeServerEmbedConfig
from .openai_compat import OpenAICompatEmbedConfig

# `tei` is no longer a registered embed CHOICE (bge_server replaced the off-the-shelf TEI image).
# The runtime TeiEmbedProvider moved to the pipeline brick
# common_libs.pipeline.bricks.providers.embed (P1b inc-4b config/runtime split); only the
# (unregistered, backward-compat) TeiEmbedConfig is exported here — it is absent from the
# EmbedProviderConfig discriminated union below.
from .tei import TeiEmbedConfig

# ------------------- Discriminated Union ------------------- #
EmbedProviderConfig = build_union(get_configs("embed"))

# ------------------- Public API ------------------- #
__all__ = [
    "EmbedProvider",
    "EmbedProviderConfig",
    "BgeServerEmbedConfig",
    "OpenAICompatEmbedConfig",
    "TeiEmbedConfig",
]

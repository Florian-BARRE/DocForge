# ---------------------- Embed slot providers ---------------------- #
# Importing this package registers every provider kind (dense / sparse) in EmbedProviderRegistry.
from .base import (
    EmbedAxis,
    EmbedProvider,
    EmbedProviderConfig,
    EmbedRole,
    RemoteEmbedProviderConfig,
)
from .bge_server import BgeServerProvider, BgeServerProviderConfig
from .bm25_local import Bm25LocalProvider, Bm25LocalProviderConfig
from .openai_compatible import OpenAICompatibleProvider, OpenAICompatibleProviderConfig
from .registry import EmbedProviderRegistry

# ------------------- Public API ------------------- #
__all__ = [
    "EmbedAxis",
    "EmbedRole",
    "EmbedProvider",
    "EmbedProviderConfig",
    "RemoteEmbedProviderConfig",
    "EmbedProviderRegistry",
    "BgeServerProvider",
    "BgeServerProviderConfig",
    "OpenAICompatibleProvider",
    "OpenAICompatibleProviderConfig",
    "Bm25LocalProvider",
    "Bm25LocalProviderConfig",
]

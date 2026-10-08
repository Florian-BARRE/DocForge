# ---------------------- Shared embedder contract ---------------------- #
from .config import BaseEmbedConfig
from .io import EmbedConsumes, EmbedProduces
from .node import BaseEmbedderNode
from .policy import EmbedCallPolicy

# ------------------- Public API ------------------- #
__all__ = [
    "BaseEmbedConfig",
    "EmbedConsumes",
    "EmbedProduces",
    "BaseEmbedderNode",
    "EmbedCallPolicy",
]

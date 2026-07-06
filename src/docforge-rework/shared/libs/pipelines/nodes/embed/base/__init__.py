# ---------------------- Shared embedder contract ---------------------- #
from .config import BaseEmbedConfig
from .io import EmbedConsumes, EmbedProduces
from .node import BaseEmbedderNode

# ------------------- Public API ------------------- #
__all__ = ["BaseEmbedConfig", "EmbedConsumes", "EmbedProduces", "BaseEmbedderNode"]

# ------------------- Config (triggers @register decorator) ------------------- #
from .config import TeiEmbedConfig

# ------------------- Provider ------------------- #
from .provider import TeiEmbedProvider

# ------------------- Public API ------------------- #
__all__ = [
    "TeiEmbedConfig",
    "TeiEmbedProvider",
]

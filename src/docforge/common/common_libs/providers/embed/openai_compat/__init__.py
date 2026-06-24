# ------------------- Config (triggers @register decorator) ------------------- #
from .config import OpenAICompatEmbedConfig

# ------------------- Provider ------------------- #
from .provider import OpenAICompatEmbedProvider

# ------------------- Public API ------------------- #
__all__ = [
    "OpenAICompatEmbedConfig",
    "OpenAICompatEmbedProvider",
]

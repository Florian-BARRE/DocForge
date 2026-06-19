# ------------------- Local Embed Providers ------------------- #
from .tei import TeiEmbedProvider
from .openai_compat import LocalOpenAICompatEmbedProvider

# ------------------- Config (triggers @register decorator) ------------------- #
from .config import TeiEmbedConfig

# ------------------- Public API ------------------- #
__all__ = [
    "LocalOpenAICompatEmbedProvider",
    "TeiEmbedConfig",
    "TeiEmbedProvider",
]

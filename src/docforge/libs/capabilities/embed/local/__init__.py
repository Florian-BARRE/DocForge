# ------------------- Local Embed Providers ------------------- #
# ------------------- Config (triggers @register decorator) ------------------- #
from .config import TeiEmbedConfig
from .openai_compat import LocalOpenAICompatEmbedProvider
from .tei import TeiEmbedProvider

# ------------------- Public API ------------------- #
__all__ = [
    "LocalOpenAICompatEmbedProvider",
    "TeiEmbedConfig",
    "TeiEmbedProvider",
]

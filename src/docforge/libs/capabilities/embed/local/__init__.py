# ------------------- Local Embed Providers ------------------- #
# ------------------- Config (triggers @register decorator) ------------------- #
from .config import TeiEmbedConfig
from .openai_compat import LocalOpenAICompatEmbedProvider
from .openai_compat_config import LocalOpenAIEmbedConfig
from .tei import TeiEmbedProvider

# ------------------- Public API ------------------- #
__all__ = [
    "LocalOpenAICompatEmbedProvider",
    "LocalOpenAIEmbedConfig",
    "TeiEmbedConfig",
    "TeiEmbedProvider",
]

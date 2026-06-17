# ------------------- Local Embed Providers ------------------- #
from .tei import TeiEmbedProvider
from .openai_compat import LocalOpenAICompatEmbedProvider

# ------------------- Public API ------------------- #
__all__ = [
    "TeiEmbedProvider",
    "LocalOpenAICompatEmbedProvider",
]

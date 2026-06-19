# ------------------- External Embed Providers ------------------- #
from .openai_compat import OpenAIEmbedProvider
from .openai_compat_config import OpenAIEmbedConfig

# ------------------- Public API ------------------- #
__all__ = [
    "OpenAIEmbedConfig",
    "OpenAIEmbedProvider",
]

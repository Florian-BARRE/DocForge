# ------------------- Config (triggers @register decorator) ------------------- #
from .config import OpenAICompatLLMConfig

# ------------------- Provider ------------------- #
from .provider import OpenAICompatLLMProvider

# ------------------- Public API ------------------- #
__all__ = [
    "OpenAICompatLLMConfig",
    "OpenAICompatLLMProvider",
]

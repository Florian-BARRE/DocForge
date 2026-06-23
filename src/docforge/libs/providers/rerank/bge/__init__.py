# ------------------- Config (triggers @register decorator) ------------------- #
from .config import BgeRerankerConfig

# ------------------- Provider ------------------- #
from .provider import BgeRerankProvider

# ------------------- Public API ------------------- #
__all__ = ["BgeRerankerConfig", "BgeRerankProvider"]

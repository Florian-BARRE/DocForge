# ------------------- Config (triggers @register decorator) ------------------- #
from .config import PaddleOcrConfig

# ------------------- Provider ------------------- #
from .provider import PaddleOcrProvider

# ------------------- Public API ------------------- #
__all__ = ["PaddleOcrConfig", "PaddleOcrProvider"]

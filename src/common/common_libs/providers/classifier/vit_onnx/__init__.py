# ------------------- Config (triggers @register decorator) ------------------- #
from .config import VitOnnxConfig

# ------------------- Provider ------------------- #
from .provider import VitOnnxClassifier

# ------------------- Public API ------------------- #
__all__ = ["VitOnnxConfig", "VitOnnxClassifier"]

# ------------------- Config (triggers @register decorator) ------------------- #
from .config import LayoutLabelsConfig

# ------------------- Provider ------------------- #
from .provider import LayoutLabelsClassifier

# ------------------- Public API ------------------- #
__all__ = ["LayoutLabelsConfig", "LayoutLabelsClassifier"]

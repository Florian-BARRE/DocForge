# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all figure classifiers and build the discriminated union.
# ─────────────────────────────────────────────────────────────────────────────

from libs.capabilities._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import ClassificationResult, FigureClassifier

# ------------------- Local Providers ------------------- #
from .local.layout_labels import LayoutLabelsClassifier, LayoutLabelsConfig
from .local.vit_onnx import VitOnnxClassifier, VitOnnxConfig

# ------------------- Discriminated Union ------------------- #
ClassifierConfig = build_union(get_configs("classifier"))

# ------------------- Public API ------------------- #
__all__ = [
    "ClassificationResult",
    "ClassifierConfig",
    "FigureClassifier",
    "LayoutLabelsClassifier",
    "LayoutLabelsConfig",
    "VitOnnxClassifier",
    "VitOnnxConfig",
]

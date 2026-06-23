# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all figure classifiers and build the discriminated union.
# ─────────────────────────────────────────────────────────────────────────────

from libs.config.pipeline._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import ClassificationResult, FigureClassifier

# ------------------- Providers (one folder each) ------------------- #
from .layout_labels import LayoutLabelsClassifier, LayoutLabelsConfig
from .vit_onnx import VitOnnxClassifier, VitOnnxConfig

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

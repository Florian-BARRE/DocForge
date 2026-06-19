# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all figure classifiers and build the discriminated union.
# ─────────────────────────────────────────────────────────────────────────────

from libs.config.pipeline._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import ClassificationResult, FigureClassifier

# ------------------- Local Providers ------------------- #
from .local.layout_labels import LayoutLabelsClassifier
from .local.layout_labels_config import LayoutLabelsConfig
from .local.vit_onnx import VitOnnxClassifier
from .local.vit_onnx_config import VitOnnxConfig

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

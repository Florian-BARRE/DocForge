# ------------------- Local Classifier Providers ------------------- #
from .layout_labels import LayoutLabelsClassifier
from .layout_labels_config import LayoutLabelsConfig
from .vit_onnx import VitOnnxClassifier
from .vit_onnx_config import VitOnnxConfig

# ------------------- Public API ------------------- #
__all__ = [
    "LayoutLabelsClassifier",
    "LayoutLabelsConfig",
    "VitOnnxClassifier",
    "VitOnnxConfig",
]

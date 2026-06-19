# ------------------- Local Classifier Providers ------------------- #
from .layout_labels import LayoutLabelsClassifier
from .vit_onnx import VitOnnxClassifier

# ------------------- Public API ------------------- #
__all__ = [
    "LayoutLabelsClassifier",
    "VitOnnxClassifier",
]

# ------------------- Classifier runtimes ------------------- #
from .layout_labels.provider import LayoutLabelsClassifier
from .vit_onnx.provider import VitOnnxClassifier

__all__ = ["LayoutLabelsClassifier", "VitOnnxClassifier"]

# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all figure classifiers and build the discriminated union.
# ─────────────────────────────────────────────────────────────────────────────

import importlib

from common_libs.config.pipeline._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import ClassificationResult, FigureClassifier

# ------------------- Providers (one folder each) ------------------- #
from .layout_labels import LayoutLabelsConfig
from .vit_onnx import VitOnnxConfig

# ------------------- Discriminated Union ------------------- #
ClassifierConfig = build_union(get_configs("classifier"))

# ------------------- Runtime re-exports (lazy) ------------------- #
# Runtime classifiers are re-exported lazily (PEP 562) so importing this package for config
# auto-discovery never eagerly pulls a heavy runtime dependency (e.g. onnxruntime) into the
# lightweight app image. Each name is imported only when first accessed (typically inside the
# matching Config.build()), preserving the config/runtime layering.
_RUNTIME_EXPORTS = {
    "LayoutLabelsClassifier": (".layout_labels.provider", "LayoutLabelsClassifier"),
    "VitOnnxClassifier": (".vit_onnx.provider", "VitOnnxClassifier"),
}


def __getattr__(name: str):
    """Lazily import and return a runtime classifier re-exported by this package."""
    target = _RUNTIME_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(target[0], __name__)
    return getattr(module, target[1])


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

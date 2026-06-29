# ------------------- Contracts only (L1) ------------------- #
# This package now exposes ONLY provider CONTRACTS — the Protocol interfaces, result dataclasses,
# device value-types, and the classifier result/base. The provider RUNTIME implementations live in
# the per-family runtime modules (common_libs.providers.<family>); import any runtime from its own
# family module, never from this top-level package, to preserve the layering. The @register provider
# CONFIG classes stay in their per-family config.py modules (discovered via auto_import).

# ------------------- Provider Protocol interfaces ------------------- #
from .interfaces import (
    ConverterProvider,
    ConvertResult,
    EmbedProvider,
    EmbedResult,
    OcrHint,
    OcrProvider,
    OcrResult,
    ParserProvider,
    RerankProvider,
    RerankResult,
    VlmProvider,
    VlmResult,
)

# ------------------- Device value-types ------------------- #
from .device import Device, DeviceCapability, DeviceSnapshot

# ------------------- Classifier contracts ------------------- #
from .classifier import ClassificationResult, FigureClassifier

# ------------------- Public API ------------------- #
__all__ = [
    "ClassificationResult",
    "ConvertResult",
    "ConverterProvider",
    "Device",
    "DeviceCapability",
    "DeviceSnapshot",
    "EmbedProvider",
    "EmbedResult",
    "FigureClassifier",
    "OcrHint",
    "OcrProvider",
    "OcrResult",
    "ParserProvider",
    "RerankProvider",
    "RerankResult",
    "VlmProvider",
    "VlmResult",
]

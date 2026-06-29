# ------------------- Contracts only (L1) ------------------- #
# This package now exposes ONLY provider CONTRACTS — the Protocol interfaces, result dataclasses,
# device value-types, and the classifier result/base. The provider RUNTIME implementations moved to
# the pipeline bricks (common_libs.pipeline.bricks.providers.<family>) in the P1b inc-4b config/
# runtime split; the Chain brick moved to common_libs.pipeline.bricks.chain (inc-4a). Import any
# runtime from the bricks, never from this package. The @register provider CONFIG classes stay in
# their per-family config.py modules (discovered via auto_import) and are imported from there.

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

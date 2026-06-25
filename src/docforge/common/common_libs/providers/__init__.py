# ------------------- Interfaces ------------------- #
# ------------------- Chain ------------------- #
from .chain import Chain

# ------------------- Converter ------------------- #
from .converter import GOTENBERG_FORMATS, NATIVE_PDF_FORMATS, GotenbergConverter

# ------------------- Device Manager ------------------- #
from .device import Device, DeviceCapability, DeviceManager
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

# ------------------- OCR Providers (P3) ------------------- #
from .ocr import MistralOcrProvider, PaddleOcrProvider

# ------------------- Parser ------------------- #
from .parser import DoclingBackend

# ------------------- VLM Providers (P3) ------------------- #
from .vlm import OpenAICompatVlmProvider

# ------------------- Classifier (P3) ------------------- #
from .classifier import (
    ClassificationResult,
    FigureClassifier,
    LayoutLabelsClassifier,
    VitOnnxClassifier,
)

# ------------------- Embed Providers (P4) ------------------- #
from .embed import CompositeEmbedProvider, OpenAICompatEmbedProvider, TeiEmbedProvider

# ------------------- Public API ------------------- #
__all__ = [
    "ClassificationResult",
    "ConvertResult",
    "ConverterProvider",
    "Device",
    "DeviceCapability",
    "DeviceManager",
    "DoclingBackend",
    "EmbedProvider",
    "EmbedResult",
    "FigureClassifier",
    "GOTENBERG_FORMATS",
    "GotenbergConverter",
    "LayoutLabelsClassifier",
    "CompositeEmbedProvider",
    "MistralOcrProvider",
    "NATIVE_PDF_FORMATS",
    "OcrHint",
    "OcrProvider",
    "OcrResult",
    "OpenAICompatEmbedProvider",
    "OpenAICompatVlmProvider",
    "PaddleOcrProvider",
    "ParserProvider",
    "Chain",
    "RerankProvider",
    "RerankResult",
    "TeiEmbedProvider",
    "VitOnnxClassifier",
    "VlmProvider",
    "VlmResult",
]

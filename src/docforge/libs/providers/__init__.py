# ------------------- Interfaces ------------------- #
# ------------------- Chain ------------------- #
from .chain import ProviderChain

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
from .vlm import LocalOpenAICompatVlmProvider, OpenAIVlmProvider

# Backward-compat alias
OpenAICompatVlmProvider = LocalOpenAICompatVlmProvider

# ------------------- Classifier (P3) ------------------- #
from .classifier import (
    ClassificationResult,
    FigureClassifier,
    LayoutLabelsClassifier,
    VitOnnxClassifier,
)

# ------------------- Embed Providers (P4) ------------------- #
from .embed import LocalOpenAICompatEmbedProvider, OpenAIEmbedProvider, TeiEmbedProvider

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
    "LocalOpenAICompatEmbedProvider",
    "LocalOpenAICompatVlmProvider",
    "MistralOcrProvider",
    "NATIVE_PDF_FORMATS",
    "OcrHint",
    "OcrProvider",
    "OcrResult",
    "OpenAICompatVlmProvider",
    "OpenAIEmbedProvider",
    "OpenAIVlmProvider",
    "PaddleOcrProvider",
    "ParserProvider",
    "ProviderChain",
    "RerankProvider",
    "RerankResult",
    "TeiEmbedProvider",
    "VitOnnxClassifier",
    "VlmProvider",
    "VlmResult",
]

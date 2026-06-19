# ------------------- Protocols ------------------- #
# ----------- Result types (re-exported) ----------- #
# Re-exported so callers that import from libs.capabilities.interfaces continue to work
# without modification (e.g. `from libs.capabilities.interfaces import ConvertResult`).
from libs.capabilities.results import (
    ConvertResult,
    EmbedResult,
    OcrHint,
    OcrResult,
    RerankResult,
    VlmResult,
)

from .converter_provider import ConverterProvider
from .embed_provider import EmbedProvider
from .ocr_provider import OcrProvider
from .parser_provider import ParserProvider
from .rerank_provider import RerankProvider
from .vlm_provider import VlmProvider

# ------------------- Public API ------------------- #
__all__ = [
    # Protocols
    "ConverterProvider",
    "EmbedProvider",
    "OcrProvider",
    "ParserProvider",
    "RerankProvider",
    "VlmProvider",
    # Result types
    "ConvertResult",
    "EmbedResult",
    "OcrHint",
    "OcrResult",
    "RerankResult",
    "VlmResult",
]

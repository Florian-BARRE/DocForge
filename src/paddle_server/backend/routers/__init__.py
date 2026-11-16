# ------------------- Layout Parsing ------------------- #
from .layout_parsing.router import LayoutParsingRoutes

# ------------------- OCR ------------------- #
from .ocr.router import OcrRoutes

# ------------------- VL Parsing ------------------- #
from .vl_parsing.router import VlParsingRoutes

# ------------------- Public API ------------------- #
__all__ = [
    "LayoutParsingRoutes",
    "OcrRoutes",
    "VlParsingRoutes",
]

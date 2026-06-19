# ------------------- Local OCR Providers ------------------- #
from .paddle_ocr import PaddleOcrProvider
from .paddle_ocr_config import PaddleOcrConfig

# ------------------- Public API ------------------- #
__all__ = [
    "PaddleOcrConfig",
    "PaddleOcrProvider",
]

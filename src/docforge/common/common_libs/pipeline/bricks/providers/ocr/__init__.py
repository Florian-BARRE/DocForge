# ------------------- OCR runtimes ------------------- #
from .mistral.provider import MistralOcrProvider
from .paddle.provider import PaddleOcrProvider

__all__ = ["PaddleOcrProvider", "MistralOcrProvider"]

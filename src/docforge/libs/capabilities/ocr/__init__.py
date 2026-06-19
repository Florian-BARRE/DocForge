# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all OCR providers and build the discriminated union.
# ─────────────────────────────────────────────────────────────────────────────

from libs.capabilities._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import OcrProvider

# ------------------- Local Providers ------------------- #
from .local.paddle_ocr import PaddleOcrConfig, PaddleOcrProvider

# ------------------- External Providers ------------------- #
from .external.mistral_ocr import MistralOcrConfig, MistralOcrProvider

# ------------------- Discriminated Union ------------------- #
OcrProviderConfig = build_union(get_configs("ocr"))

# ------------------- Public API ------------------- #
__all__ = [
    "MistralOcrConfig",
    "MistralOcrProvider",
    "OcrProvider",
    "OcrProviderConfig",
    "PaddleOcrConfig",
    "PaddleOcrProvider",
]

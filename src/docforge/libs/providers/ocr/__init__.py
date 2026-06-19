# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all OCR providers and build the discriminated union.
# ─────────────────────────────────────────────────────────────────────────────

from libs.core.contracts._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import OcrProvider

# ------------------- External Providers ------------------- #
from .external.mistral_ocr import MistralOcrProvider
from .external.mistral_ocr_config import MistralOcrConfig

# ------------------- Local Providers ------------------- #
from .local.paddle_ocr import PaddleOcrProvider
from .local.paddle_ocr_config import PaddleOcrConfig

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

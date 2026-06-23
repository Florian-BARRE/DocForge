# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all OCR providers and build the discriminated union.
# One folder per provider (paddle = local GPU/CPU, mistral = cloud API); each provider's
# fixed deployment lives in its runs_on class attribute, not a user-editable locality flag.
# ─────────────────────────────────────────────────────────────────────────────

from libs.config.pipeline._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import OcrProvider

# ------------------- Providers (one folder each) ------------------- #
from .mistral import MistralOcrConfig, MistralOcrProvider
from .paddle import PaddleOcrConfig, PaddleOcrProvider

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

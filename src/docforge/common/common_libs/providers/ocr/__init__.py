# ─────────────────────────────────────────────────────────────────────────────
# Auto-discover all OCR providers and build the discriminated union.
# One folder per provider (paddle = local GPU/CPU, mistral = cloud API); each provider's
# fixed deployment lives in its runs_on class attribute, not a user-editable locality flag.
# ─────────────────────────────────────────────────────────────────────────────

import importlib

from common_libs.config.pipeline._registry import auto_import, build_union, get_configs

auto_import(__name__)

# ---------------------- Base ---------------------- #
from .base import OcrProvider

# ------------------- Providers (one folder each) ------------------- #
from .mistral import MistralOcrConfig
from .paddle import PaddleOcrConfig

# ------------------- Discriminated Union ------------------- #
OcrProviderConfig = build_union(get_configs("ocr"))

# ------------------- Runtime re-exports (lazy) ------------------- #
# Runtime providers are re-exported lazily (PEP 562) so importing this package for config
# auto-discovery never eagerly pulls a heavy runtime dependency (e.g. paddleocr) into the
# lightweight app image. Each name is imported only when first accessed (typically inside the
# matching Config.build()), preserving the config/runtime layering.
_RUNTIME_EXPORTS = {
    "MistralOcrProvider": (".mistral.provider", "MistralOcrProvider"),
    "PaddleOcrProvider": (".paddle.provider", "PaddleOcrProvider"),
}


def __getattr__(name: str):
    """Lazily import and return a runtime provider re-exported by this package."""
    target = _RUNTIME_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(target[0], __name__)
    return getattr(module, target[1])


# ------------------- Public API ------------------- #
__all__ = [
    "MistralOcrConfig",
    "MistralOcrProvider",
    "OcrProvider",
    "OcrProviderConfig",
    "PaddleOcrConfig",
    "PaddleOcrProvider",
]

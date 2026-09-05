# ---------------------- OpenAI-compatible endpoint access (shared) ---------------------- #
from .client import OpenAICompatHelpers, UsageAccumulator
from .config import OpenAICompatConfig
from .preflight import (
    EndpointAuthError,
    EndpointReachability,
    EndpointUnreachableError,
    PreflightError,
)
from .pricing import EMBED_PRICING, MODEL_PRICING, OCR_PAGE_PRICING, price_ocr_pages, price_usd

# ------------------- Public API ------------------- #
__all__ = [
    "OpenAICompatConfig",
    "OpenAICompatHelpers",
    "UsageAccumulator",
    "EndpointReachability",
    "PreflightError",
    "EndpointUnreachableError",
    "EndpointAuthError",
    "MODEL_PRICING",
    "EMBED_PRICING",
    "OCR_PAGE_PRICING",
    "price_usd",
    "price_ocr_pages",
]

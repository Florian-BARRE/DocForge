# ---------------------- OpenAI-compatible endpoint access (shared) ---------------------- #
from .client import OpenAICompatHelpers, UsageAccumulator
from .client_pool import LangChainClientPool
from .config import OpenAICompatConfig
from .preflight import (
    EndpointAuthError,
    EndpointIncompatibleError,
    EndpointReachability,
    EndpointUnreachableError,
    PreflightError,
)
from .pricing import EMBED_PRICING, MODEL_PRICING, OCR_PAGE_PRICING, price_ocr_pages, price_usd

# ------------------- Public API ------------------- #
__all__ = [
    "OpenAICompatConfig",
    "OpenAICompatHelpers",
    "LangChainClientPool",
    "UsageAccumulator",
    "EndpointReachability",
    "PreflightError",
    "EndpointUnreachableError",
    "EndpointAuthError",
    "EndpointIncompatibleError",
    "MODEL_PRICING",
    "EMBED_PRICING",
    "OCR_PAGE_PRICING",
    "price_usd",
    "price_ocr_pages",
]

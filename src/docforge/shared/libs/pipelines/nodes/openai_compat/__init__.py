# ---------------------- OpenAI-compatible endpoint access (shared) ---------------------- #
from .client import OpenAICompatHelpers
from .config import OpenAICompatConfig
from .preflight import (
    EndpointAuthError,
    EndpointReachability,
    EndpointUnreachableError,
    PreflightError,
)
from .pricing import EMBED_PRICING, MODEL_PRICING, OCR_PAGE_PRICING, price_usd

# ------------------- Public API ------------------- #
__all__ = [
    "OpenAICompatConfig",
    "OpenAICompatHelpers",
    "EndpointReachability",
    "PreflightError",
    "EndpointUnreachableError",
    "EndpointAuthError",
    "MODEL_PRICING",
    "EMBED_PRICING",
    "OCR_PAGE_PRICING",
    "price_usd",
]

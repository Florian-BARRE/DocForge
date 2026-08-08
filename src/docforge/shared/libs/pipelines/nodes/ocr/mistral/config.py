# ====== Code Summary ======
# Config of the Mistral OCR node — the ROBUST tail of an OCR escalation: the hosted document-OCR
# API. Endpoint + key + model go through config like every provider (defaults overridable per
# collection).

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import TimeoutRetryConfig

# ====== Local Project Imports ======
from ..base import BaseOcrConfig


class OcrMistralConfig(BaseOcrConfig, TimeoutRetryConfig):
    """Mistral OCR API endpoint + model.

    The local OCR base (``BaseOcrConfig``) stays empty — rapidocr makes no network call — so only
    THIS hosted provider mixes in the timeout/retry surface (``timeout_seconds`` overridden to 120 s
    for document OCR). Retry runs through the shared ``NetworkRetry`` loop in the node.
    """

    base_url: str = Field(default="https://api.mistral.ai/v1", description="Mistral API base URL.")
    api_key: str = Field(description="Mistral API key.")
    model: str = Field(default="mistral-ocr-latest", description="OCR model name.")
    timeout_seconds: float = Field(default=120.0, gt=0, description="Per-request timeout (s).")


__all__ = ["OcrMistralConfig"]

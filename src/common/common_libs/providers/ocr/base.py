# ====== Code Summary ======
# Abstract base class for all OCR providers.
# Every OCR provider takes image bytes and returns extracted text + confidence.

from __future__ import annotations

from abc import ABC, abstractmethod

from common_libs.providers.interfaces import OcrHint, OcrResult


class OcrProvider(ABC):
    """
    Abstract base class for all OCR providers.

    OCR providers extract text from image regions (figure crops, page scans).
    They participate in ProviderChain escalation: when confidence falls below
    the chain threshold the next provider in the list is tried.

    Class attributes:
        name (str): Provider identifier used in logs.
        version (str): OCR engine version string.
        runs_on (str): \"local\" (GPU/CPU) or \"remote\" (cloud API).
        cost_per_page (float): Estimated USD cost per page — 0.0 for local providers.
    """

    name: str
    version: str
    runs_on: str
    cost_per_page: float

    @abstractmethod
    async def extract(self, img_bytes: bytes, hint: OcrHint) -> OcrResult:
        """
        Run OCR on a single image and return the extracted text.

        Args:
            img_bytes (bytes): PNG or JPEG image bytes.
            hint (OcrHint): Optional language and DPI context.

        Returns:
            OcrResult: Extracted text with a confidence score in [0, 1].
                confidence < threshold triggers escalation to the next provider.
        """
        ...

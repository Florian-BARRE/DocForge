# ====== Code Summary ======
# OcrProvider Protocol — defines the interface for OCR backends that extract text from
# image regions (page scans, figures, etc.). Local and remote providers are interchangeable.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Protocol, runtime_checkable

# ====== Third-Party Library Imports ======
# (none — Protocol and result types only)
# ====== Internal Project Imports ======
from libs.providers.results import OcrHint, OcrResult

# ====== Local Project Imports ======
# (none)


@runtime_checkable
class OcrProvider(Protocol):
    """Extracts text from an image region (page scan, figure, etc.)."""

    name: str
    version: str
    runs_on: str        # "cpu" | "gpu" | "remote"
    cost_per_page: float  # 0.0 for local providers

    async def extract(self, img_bytes: bytes, hint: OcrHint) -> OcrResult:
        """
        Run OCR on a single image.

        Args:
            img_bytes (bytes): PNG or JPEG image bytes.
            hint (OcrHint): Optional language / DPI context.

        Returns:
            OcrResult: Extracted text with confidence score.
        """
        ...

# ====== Code Summary ======
# Mistral OCR API adapter — cloud OCR provider for high-quality text extraction.
# Used as escalation fallback when local OCR confidence is below the chain threshold.
# Sends the image as a base64 data-URI to the Mistral OCR REST endpoint.
# Config class has been extracted to mistral_ocr_config.py to avoid circular imports.

from __future__ import annotations

import base64

import httpx
from loggerplusplus import LoggerClass

from common_libs.providers.interfaces import OcrHint, OcrResult
from common_libs.providers.ocr.base import OcrProvider


class MistralOcrProvider(OcrProvider, LoggerClass):
    """
    OCR provider backed by the Mistral OCR API.

    Positioned as the second link in an OcrProviderChain — called only when
    the local provider (PaddleOCR) returns low-confidence results.

    The API does not expose per-character confidence; the returned confidence
    is always 1.0 to prevent further escalation (API result is treated as final).

    Config id: "mistral_ocr" (external API — api_key required)
    """

    name: str = "mistral-ocr"
    version: str = "latest"
    runs_on: str = "remote"

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://api.mistral.ai/v1",
        model: str = "mistral-ocr-latest",
        timeout_s: int = 60,
    ) -> None:
        """
        Initialize the Mistral OCR provider.

        Args:
            api_key (str): Mistral API key (kept in RUNTIME_CONFIG, never in code).
            api_url (str): Base URL of the Mistral API.
            model (str): OCR model identifier.
            timeout_s (int): HTTP request timeout in seconds.
        """
        LoggerClass.__init__(self)
        self._api_url = api_url.rstrip("/")
        self._model = model
        self._timeout_s = timeout_s
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def extract(self, img_bytes: bytes, hint: OcrHint) -> OcrResult:
        """
        Extract text from an image via the Mistral OCR API.

        The image is base64-encoded and sent as a data-URI in the request body.

        Args:
            img_bytes (bytes): PNG or JPEG image bytes.
            hint (OcrHint): Language context (currently unused by the Mistral endpoint).

        Returns:
            OcrResult: Concatenated markdown text from all returned pages;
                confidence=1.0 (API result is treated as authoritative).
        """
        self.logger.debug(f"Mistral OCR API call: model={self._model!r}")

        # 1. Encode image as base64 data-URI (Mistral OCR API format)
        b64 = base64.b64encode(img_bytes).decode("ascii")
        data_uri = f"data:image/png;base64,{b64}"

        # 2. Build request payload
        payload = {
            "model": self._model,
            "document": {
                "type": "image_url",
                "image_url": data_uri,
            },
        }

        # 3. POST to Mistral OCR endpoint
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            response = await client.post(
                f"{self._api_url}/ocr",
                headers=self._headers,
                json=payload,
            )
            response.raise_for_status()

        # 4. Parse response — Mistral OCR returns pages[].markdown
        data = response.json()
        pages = data.get("pages", [])
        text_parts: list[str] = [
            page["markdown"].strip()
            for page in pages
            if page.get("markdown", "").strip()
        ]

        full_text = "\n\n".join(text_parts)
        self.logger.debug(
            f"Mistral OCR: {len(pages)} page(s) extracted "
            f"({len(full_text)} chars)"
        )

        # Confidence=1.0: no score from API; prevents further escalation in the chain
        return OcrResult(text=full_text, confidence=1.0)

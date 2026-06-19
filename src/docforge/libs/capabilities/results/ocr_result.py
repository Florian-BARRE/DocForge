# ====== Code Summary ======
# OcrHint and OcrResult Pydantic models for OCR provider interactions.
# OcrHint is passed to the provider as input context; OcrResult carries the
# extracted text and confidence score used by the chain escalation gate.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Internal Project Imports ======
# (none)

# ====== Local Project Imports ======
# (none)


class OcrHint(BaseModel):
    """
    Context passed to an OCR provider to guide extraction.

    Attributes:
        language (str | None): ISO 639-1 language code hint, or None if unknown.
        dpi (int): Image resolution used for OCR. Defaults to 300.
    """

    language: str | None = None
    dpi: int = 300


class OcrResult(BaseModel):
    """
    Output of an OCR call on a single image region.

    Attributes:
        text (str): Extracted text content.
        confidence (float): Per-character average confidence in [0, 1],
            used by the chain gate to decide whether to escalate to the next provider.
        language (str | None): Detected language, if available from the provider.
    """

    text: str
    confidence: float  # [0, 1] — used to decide escalation in the provider chain
    language: str | None = None

    def score(self) -> float | None:
        """
        Return the escalation score for the chain gate.

        Returns:
            float | None: The provider's average per-character confidence.
        """
        return self.confidence

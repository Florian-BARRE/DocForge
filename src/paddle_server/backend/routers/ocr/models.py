# ====== Code Summary ======
# Pydantic response model for POST /ocr — the sidecar's OCR-only contract. Request body is raw image
# bytes (Content-Type: image/png), not a pydantic model — there are no request knobs (lang and
# textline-orientation are pipeline-level, set at build). The response is a single joined reading +
# one aggregate confidence, consumed by the DocForge OcrPaddleNode behind the `ocr` family contract.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class OcrResponse(BaseModel):
    """
    Full response body of `POST /ocr`.

    Attributes:
        text (str): The newline-joined recognized text of the image (empty when nothing was read).
        confidence (float): Mean per-line recognition confidence in [0, 1] (0.0 when empty) — the
            value a DocForge ScoreBelow transition escalates on.
    """

    text: str = Field(..., description="Newline-joined recognized text (empty when nothing read).")
    confidence: float = Field(
        ..., description="Mean per-line recognition confidence in [0, 1] (0.0 when empty)."
    )


__all__ = ["OcrResponse"]

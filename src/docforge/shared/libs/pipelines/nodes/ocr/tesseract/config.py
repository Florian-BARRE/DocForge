# ====== Code Summary ======
# Config of the Tesseract node — a LOCAL, OFFLINE OCR provider (the tesseract engine shells out to
# the installed binary, no endpoint, no secret). Its only knobs are Tesseract's own: the language
# code(s) that drive its broad-language recognition, and the page-segmentation mode. The confidence
# gate stays on the graph (a ScoreBelow transition), never in the config.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Local Project Imports ======
from ..base import BaseOcrConfig


class OcrTesseractConfig(BaseOcrConfig):
    """Tesseract language + page-segmentation knobs (local, offline; escalation lives on the graph)."""

    lang: str = Field(
        default="eng",
        description="Tesseract language code(s) to load, '+'-joined for multi-language OCR "
        "(e.g. 'eng', 'eng+fra'). This is the whole point of the provider — broad language "
        "support. Each code must have its data pack installed in the worker image "
        "(tesseract-ocr-<code>).",
    )
    psm: int = Field(
        default=3,
        ge=0,
        le=13,
        description="Tesseract page-segmentation mode (--psm). 3 = fully automatic page "
        "segmentation (the default, best for a whole figure crop); 6 assumes a single uniform "
        "block of text.",
    )


__all__ = ["OcrTesseractConfig"]

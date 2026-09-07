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
        default="auto",
        description="Tesseract language code(s) to load. 'auto' (the recommended default) uses "
        "DocForge's already-detected document language — the figure's ISO 639-1 code is mapped "
        "to its Tesseract pack (falling back to 'eng' when the language is unknown or has no "
        "shipped pack). An explicit code is honoured verbatim and may be '+'-joined for "
        "multi-language OCR (e.g. 'eng', 'eng+fra'). Each explicit code must have its data pack "
        "installed in the worker image (tesseract-ocr-<code>).",
    )
    psm: int = Field(
        default=3,
        ge=0,
        le=13,
        description="Tesseract page-segmentation mode (--psm). 3 = fully automatic page "
        "segmentation (the default, best for a whole figure crop); 6 assumes a single uniform "
        "block of text.",
    )
    oem: int = Field(
        default=3,
        ge=0,
        le=3,
        description="Tesseract OCR engine mode (--oem). 0 = legacy engine only, 1 = LSTM neural "
        "engine only, 2 = legacy + LSTM, 3 = default (whichever is available).",
    )


__all__ = ["OcrTesseractConfig"]

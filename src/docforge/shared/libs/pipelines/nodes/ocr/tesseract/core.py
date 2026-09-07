# ====== Code Summary ======
# The Tesseract node — a LOCAL, OFFLINE, broad-language OCR provider, interchangeable with
# rapidocr/paddle/mistral behind the family contract. It is a thin adapter over the process-shared
# TesseractEngine: it reads the crop with the config's language(s) + page-segmentation mode and
# reports the mean per-word confidence, which is what a ScoreBelow transition escalates on. Zero
# endpoint, zero secret (pytesseract shells out to the installed binary); no device logic.

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..base import BaseOcrNode
from .config import OcrTesseractConfig
from .engine import TesseractEngine


@NodeRegistry.register("ocr")
class OcrTesseractNode(BaseOcrNode):
    """Local, offline, broad-language OCR (Tesseract) — a cheap head or tail of an escalation."""

    KIND = "tesseract"
    NAME = "Tesseract (local)"
    SUMMARY = "Local offline OCR (Tesseract) with broad multi-language support."
    HOW_IT_WORKS = (
        "Runs the installed Tesseract binary on the crop (no endpoint, no secret) with the "
        "configured language(s) and page-segmentation mode, and reports the mean per-word "
        "confidence; a weak reading escalates via a ScoreBelow transition."
    )
    Config = OcrTesseractConfig

    async def _read(self, image: bytes, language: str) -> tuple[str, float]:
        """Read the crop through the process-shared engine → (text, mean confidence).

        With ``lang='auto'`` the effective pack is resolved from the figure's detected language;
        an explicit config code is honoured verbatim (both via the engine's single-source map).
        """
        config: OcrTesseractConfig = self.config
        lang = TesseractEngine.resolve_lang(config.lang, language)
        data = await TesseractEngine.read(image, lang=lang, psm=config.psm, oem=config.oem)
        return TesseractEngine.to_text(data)


__all__ = ["OcrTesseractNode"]

# ====== Code Summary ======
# The RapidOCR node — the cheap LOCAL head of an OCR escalation (onnxruntime CPU, models bundled).
# It is a thin adapter over the process-shared RapidOcrEngine: it reads the crop and reports the mean
# per-line confidence, which is what a ScoreBelow transition escalates on (a poor local reading routes
# to the robust provider). The engine (build-once, serialised inference, off-loop execution) is shared
# with the local figure classifier, so the native model is loaded at most once per process.

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..base import BaseOcrNode
from .config import OcrRapidOcrConfig
from .engine import RapidOcrEngine


@NodeRegistry.register("ocr")
class OcrRapidOcrNode(BaseOcrNode):
    """Local CPU OCR (RapidOCR/ONNX) — the cheap first attempt of an escalation."""

    KIND = "rapidocr"
    NAME = "RapidOCR (local)"
    SUMMARY = "Local CPU OCR — the cheap first attempt of an OCR escalation."
    HOW_IT_WORKS = (
        "Runs the bundled RapidOCR ONNX models on the crop (no endpoint, no secret) and reports "
        "the mean per-line confidence; a weak reading escalates via a ScoreBelow transition."
    )
    Config = OcrRapidOcrConfig

    async def _read(self, image: bytes) -> tuple[str, float]:
        """Read the crop through the process-shared engine → (text, mean confidence)."""
        return RapidOcrEngine.to_text(await RapidOcrEngine.read(image))


__all__ = ["OcrRapidOcrNode"]

# ====== Code Summary ======
# Config of the RapidOCR node — the cheap LOCAL head of an OCR escalation (ONNX runtime, CPU,
# models bundled with the package: zero endpoint, zero secret, zero knob). Its real per-line
# confidences are what a ScoreBelow transition escalates on.

# ====== Local Project Imports ======
from ..base import BaseOcrConfig


class OcrRapidOcrConfig(BaseOcrConfig):
    """RapidOCR has no endpoint and no knob — the confidence gate lives on the graph."""


__all__ = ["OcrRapidOcrConfig"]

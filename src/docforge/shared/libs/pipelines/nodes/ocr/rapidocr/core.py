# ====== Code Summary ======
# The RapidOCR node — the cheap LOCAL head of an OCR escalation (onnxruntime CPU, models bundled).
# Lazy-imports rapidocr (native dep, worker image), shares ONE engine process-wide (built once),
# and runs the CPU-bound reading off the event loop. Reports the mean per-line confidence, which
# is what a ScoreBelow transition escalates on: a poor local reading routes to the robust provider.

# ====== Standard Library Imports ======
import asyncio
import threading
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..base import BaseOcrNode
from .config import OcrRapidOcrConfig


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

    # ONE engine per process — model load happens once, every node instance reuses it.
    _engine: Any = None
    _engine_lock = threading.Lock()
    # The RapidOCR wrapper holds mutable pre/post state, so its inference is NOT re-entrant across
    # threads. Concurrent jobs + the per-figure enrich ForEach both fan reads onto to_thread workers
    # that share this one engine — serialise the sync call to avoid latent state corruption. The lock
    # lives inside the worker thread only, so the async event loop is never blocked.
    _inference_lock = threading.Lock()

    @classmethod
    def __resolve_engine(cls) -> Any:
        """Build the process-shared RapidOCR engine on first use (lazy native import)."""
        with cls._engine_lock:
            if cls._engine is None:
                from rapidocr_onnxruntime import RapidOCR

                cls._engine = RapidOCR()
        return cls._engine

    def __read_sync(self, image: bytes) -> tuple[str, float]:
        """Synchronous OCR (runs in a worker thread)."""
        engine = self.__resolve_engine()
        # RapidOCR returns (list of [box, text, confidence] | None, elapse_times). Serialise the
        # call: the shared engine's mutable pre/post state is not thread-safe under concurrent reads.
        with self._inference_lock:
            readings, _elapsed = engine(image)
        if not readings:
            return "", 0.0
        lines = [entry[1] for entry in readings]
        confidences = [float(entry[2]) for entry in readings]
        return "\n".join(lines), sum(confidences) / len(confidences)

    async def _read(self, image: bytes) -> tuple[str, float]:
        """Run the CPU-bound reading off the event loop."""
        return await asyncio.to_thread(self.__read_sync, image)


__all__ = ["OcrRapidOcrNode"]

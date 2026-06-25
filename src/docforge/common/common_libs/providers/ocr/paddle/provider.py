# ====== Code Summary ======
# PaddleOCR adapter — local GPU/CPU OCR provider.
# Lazy-loads PaddleOCR models on the first extract() call to avoid slow startup.
# Inference runs in a thread pool to avoid blocking the async event loop.
# Config class has been extracted to paddle_ocr_config.py to avoid circular imports.

from __future__ import annotations

import asyncio
import io

from typing import Any

from loggerplusplus import LoggerClass

from common_libs.providers.interfaces import OcrHint, OcrResult
from common_libs.providers.model_cache import ModelCache
from common_libs.providers.ocr.base import OcrProvider


class PaddleOcrProvider(OcrProvider, LoggerClass):
    """
    Local OCR provider backed by PaddleOCR v5.

    Supports GPU (CUDA) and CPU.  Heavy model loading is lazy (deferred to the first
    extract() call).  Inference is dispatched to a thread pool.

    cost_per_page = 0.0 — PaddleOCR runs entirely on local hardware.

    Config id: "paddle_ocr"
    """

    name: str = "paddleocr"
    version: str = "5"
    cost_per_page: float = 0.0

    def __init__(self, use_gpu: bool = False, default_lang: str = "fr") -> None:
        """
        Initialize the PaddleOCR provider.

        Args:
            use_gpu (bool): If True, run detection and recognition on GPU (CUDA).
            default_lang (str): Default OCR language code (e.g. "fr", "en", "ch").
        """
        LoggerClass.__init__(self)
        self._use_gpu = use_gpu
        self._default_lang = default_lang
        self.runs_on: str = "gpu" if use_gpu else "cpu"

    async def extract(self, img_bytes: bytes, hint: OcrHint) -> OcrResult:
        """
        Run OCR on an image region.

        Args:
            img_bytes (bytes): PNG or JPEG image bytes.
            hint (OcrHint): Optional language and DPI context.

        Returns:
            OcrResult: Extracted text lines joined with newlines; average confidence.
        """
        # 1. Dispatch to thread pool — PaddleOCR is CPU-bound
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._extract_sync, img_bytes, hint)

    def _extract_sync(self, img_bytes: bytes, hint: OcrHint) -> OcrResult:
        """
        Synchronous PaddleOCR extraction (runs in thread pool).

        Raises on any engine/inference failure so the provider chain can record the failed
        attempt and ESCALATE to the next OCR provider — a crashed engine must never be masked
        as a successful empty result.  A genuinely text-free image still returns an empty
        OcrResult (the engine ran fine, it just found no text).

        Raises:
            Exception: Re-raised on any PaddleOCR import/init/inference failure.
        """
        try:
            import numpy as np  # type: ignore
            from PIL import Image  # type: ignore

            # 1. Resolve the process-shared PaddleOCR engine (loaded once per lang+device via
            # ModelCache). The language is model-determining, so it is part of the cache key —
            # an "en" request never reuses the "fr" engine.
            lang = hint.language or self._default_lang
            model_key = ("paddle_ocr.engine", lang, self._use_gpu)
            ocr = ModelCache.get_or_load(model_key, lambda: self._build_engine(lang))

            # 2. Convert bytes → numpy array (RGB)
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            arr = np.array(img)

            # 3. Run recognition. PaddleOCR is NOT thread-safe and the engine is now shared
            # across jobs, so serialize the call on the per-model lock. Acceptable: OCR is
            # CPU-bound and already dispatched to a thread pool.
            with ModelCache.lock_for(model_key):
                results = ocr.ocr(arr, cls=True)

            # 4. Aggregate text lines and compute average confidence
            lines: list[str] = []
            confidences: list[float] = []

            if results and results[0]:
                for line in results[0]:
                    # Each line: [[bbox_pts], (text, score)]
                    text, score = line[1]
                    if text and text.strip():
                        lines.append(text.strip())
                        confidences.append(float(score))

            full_text = "\n".join(lines)
            avg_confidence = (
                sum(confidences) / len(confidences) if confidences else 0.0
            )

            self.logger.debug(
                f"PaddleOCR: {len(lines)} lines extracted (avg_conf={avg_confidence:.3f})"
            )
            return OcrResult(text=full_text, confidence=avg_confidence)

        except Exception as exc:
            # Log + re-raise: the chain marks this attempt failed and escalates to the next
            # provider; an exhausted chain then returns None (handled by the S2 OCR router).
            self.logger.error(f"PaddleOCR extraction failed: {exc}")
            raise

    def _build_engine(self, lang: str) -> Any:
        """
        Build a PaddleOCR engine for the given language (the ModelCache loader — once per key).

        Args:
            lang (str): Resolved OCR language code (model-determining — part of the cache key).

        Returns:
            Any: A new ``PaddleOCR`` engine bound to ``lang`` and the configured device.

        Raises:
            RuntimeError: When the paddleocr package is not installed (not cached).
        """
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError as exc:
            raise RuntimeError(f"paddleocr is not installed. Run: uv add paddleocr") from exc

        engine = PaddleOCR(
            use_angle_cls=True,
            lang=lang,
            use_gpu=self._use_gpu,
            show_log=False,
        )
        self.logger.info(f"PaddleOCR initialized: lang={lang} gpu={self._use_gpu}")
        return engine

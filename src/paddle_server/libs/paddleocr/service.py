# ====== Code Summary ======
# Owns the single PaddleOCR (text detection + recognition) pipeline instance — the OCR-only
# capability, SEPARATE from PpStructureService's full layout pipeline (pure semantics: no layout,
# no PDF-path input, one image → one reading). Built once inside `build()`, called exclusively from
# the FastAPI lifespan — routes access it through CONTEXT. The heavy paddleocr/paddlex import is
# deferred to `build()` so importing this module never triggers the ML stack.
#
# Concurrency: PaddlePaddle inference is NOT thread-safe, so every `read_image()` call is serialized
# behind a single `asyncio.Lock` — the `predict()` call itself runs inside `asyncio.to_thread` so it
# never blocks the event loop (mirrors PpStructureService's discipline). A caller that cannot acquire
# the lock within `lock_wait_timeout` gets a `TimeoutError`, translated to HTTP 503 by the router.

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio
import os
import tempfile
import time
from typing import TYPE_CHECKING, Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.validation import InputValidator

# ====== Local Project Imports ======
from .normalizer import PaddleOcrResponseNormalizer

# TYPE_CHECKING guard keeps the paddleocr/paddlex/paddlepaddle import out of the module's
# top-level scope; the actual import happens inside build() at boot time.
if TYPE_CHECKING:
    from paddleocr import PaddleOCR


class PaddleOcrService(LoggerClass):
    """
    Manages the lifecycle of the PaddleOCR text detection+recognition pipeline (OCR-only).

    The pipeline is built once during FastAPI startup (via `build()`) and torn down at shutdown
    (via `unload()`). `use_doc_orientation_classify` and `use_doc_unwarping` are forced False (never
    accepted from a caller) — this is a pure per-crop OCR read, not a document preprocessor.
    """

    def __init__(
        self,
        lang: str,
        use_textline_orientation: bool,
        model_cache_home: str,
        model_source: str,
        lock_wait_timeout_seconds: float,
    ) -> None:
        """
        Args:
            lang (str): PADDLE_OCR_LANG — recognition language pack (e.g. "en", "fr", "ch").
            use_textline_orientation (bool): PADDLE_OCR_USE_TEXTLINE_ORIENTATION — run the
                textline-orientation classifier (helps rotated lines; extra model + latency).
            model_cache_home (str): PADDLE_PDX_CACHE_HOME — set as an env var BEFORE this process
                starts (docker compose), not applied here; kept only for the boot log.
            model_source (str): PADDLE_PDX_MODEL_SOURCE — same as above, log-only.
            lock_wait_timeout_seconds (float): Max seconds a `read_image()` call waits to acquire
                the shared predict lock before raising `TimeoutError` (-> HTTP 503).
        """
        LoggerClass.__init__(self)
        self._lang = lang
        self._use_textline_orientation = use_textline_orientation
        self._model_cache_home = model_cache_home
        self._model_source = model_source
        self._lock_wait_timeout_seconds = lock_wait_timeout_seconds

        # Serializes every predict() call — PaddlePaddle is not thread-safe (module docstring).
        self._lock = asyncio.Lock()
        # Typed attribute set by build(); None until the service is started.
        self._pipeline: PaddleOCR | None = None

    # ── Properties ────────────────────────────────────────────────────────────────

    @property
    def ready(self) -> bool:
        """
        Returns:
            bool: True once `build()` has completed and the pipeline is usable.
        """
        return self._pipeline is not None

    # ── Public methods ─────────────────────────────────────────────────────────────

    def build(self) -> None:
        """
        Construct the PaddleOCR pipeline (text detection + recognition only).

        `use_doc_orientation_classify=False` and `use_doc_unwarping=False` are passed
        unconditionally — this is a per-crop OCR read, not a document preprocessor.
        """
        # Defer the heavy paddleocr/paddlex/paddlepaddle import to this moment — the container is
        # booting, matches PpStructureService's deferred-import discipline.
        from paddleocr import PaddleOCR  # noqa: PLC0415

        self.logger.info(
            f"Building PaddleOCR pipeline: lang={self._lang}, "
            f"textline_orientation={self._use_textline_orientation}, "
            f"model_cache_home={self._model_cache_home}, model_source={self._model_source}"
        )
        t0 = time.perf_counter()
        self._pipeline = PaddleOCR(
            lang=self._lang,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=self._use_textline_orientation,
            # Disable oneDNN/MKLDNN: PaddlePaddle 3.x's PIR executor raises
            # "ConvertPirAttribute2RuntimeAttribute not support" on the CPU oneDNN path. Forcing the
            # native CPU kernels avoids it; harmless on GPU. Mirrors PpStructureService.build().
            enable_mkldnn=False,
        )
        elapsed = time.perf_counter() - t0
        self.logger.info(f"PaddleOCR pipeline built in {elapsed:.1f}s")

    def unload(self) -> None:
        """Release the pipeline reference so the GC can reclaim its memory."""
        self._pipeline = None
        self.logger.info(f"PaddleOCR pipeline unloaded")

    async def read_image(self, image_bytes: bytes) -> dict[str, Any]:
        """
        OCR one image's bytes into the sidecar's `POST /ocr` response contract.

        Steps:
          1. Acquire the shared predict lock (bounded wait -> TimeoutError -> HTTP 503).
          2. Write the image bytes to a temp file — PaddleX's `predict()` takes a path, not raw
             bytes.
          3. Run `predict()` in a worker thread (CPU/GPU-bound, must not block the event loop).
          4. Normalize the result list via `PaddleOcrResponseNormalizer`.
          5. Always clean up the temp file, even on failure.

        Args:
            image_bytes (bytes): Raw image content (the request body).

        Returns:
            dict[str, Any]: `{"text": str, "confidence": float}`.

        Raises:
            RuntimeError: If `build()` has not been called yet.
            InvalidInputError: If the body is not a decodable image (a client error -> HTTP 422).
            TimeoutError: If the predict lock cannot be acquired within the configured timeout.
        """
        if self._pipeline is None:
            raise RuntimeError(f"PaddleOcrService.build() has not been called yet.")

        # Reject an undecodable image as a client error BEFORE taking the lock or spending
        # inference — surfaces as HTTP 422, not a raw PaddleX exception leaked at HTTP 500.
        InputValidator.verify_image(image_bytes)

        # 1. Bounded wait on the shared lock — a timeout surfaces as a clear 503, not a pile-up.
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=self._lock_wait_timeout_seconds)
        except TimeoutError as exc:
            raise TimeoutError(
                f"Timed out after {self._lock_wait_timeout_seconds}s waiting for the PaddleOCR "
                f"predict lock — the service is busy."
            ) from exc

        try:
            # 2. Materialize the image to a temp file for PaddleX's path-based predict() input.
            fd, tmp_path = tempfile.mkstemp(suffix=".png")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(image_bytes)

                # 3. Run the CPU/GPU-bound predict() call off the event loop.
                t0 = time.perf_counter()
                results = await asyncio.to_thread(self._predict_sync, tmp_path)
                elapsed = time.perf_counter() - t0
            finally:
                # 5. Always clean up the temp file, even on a predict() failure.
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        finally:
            self._lock.release()

        # 4. Normalize the result list into the sidecar contract.
        reading = PaddleOcrResponseNormalizer.to_reading(list(results))
        self.logger.info(
            f"OCR'd image ({len(image_bytes)} bytes) -> {len(reading['text'])} chars "
            f"(confidence {reading['confidence']:.2f}) in {elapsed:.1f}s"
        )
        return reading

    def _predict_sync(self, image_path: str) -> list[Any]:
        """
        Synchronous predict() call — runs inside `asyncio.to_thread` (never call directly from the
        event loop).

        Args:
            image_path (str): Path to the temp image file written by `read_image()`.

        Returns:
            list[Any]: One dict-like `OCRResult` object per input image (one for a single image).
        """
        assert self._pipeline is not None  # noqa: S101 — guarded by the caller
        return self._pipeline.predict(image_path)


__all__ = ["PaddleOcrService"]

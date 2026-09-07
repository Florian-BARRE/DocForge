# ====== Code Summary ======
# Owns the single dots.ocr per-element layout VLM parse pipeline — the same lock-serialized,
# off-event-loop predict discipline as mineru_server's MineruService. dots.ocr inference is heavy
# (GPU-only, minutes per multi-page document) and not safe to run concurrently on one GPU, so every
# parse_pdf() is serialized behind a single asyncio.Lock (concurrency 1) and the actual engine call
# runs inside asyncio.to_thread so it never blocks the event loop. A caller that cannot acquire the
# lock within lock_wait_timeout gets a TimeoutError -> HTTP 503.
#
# This service is PURE-ish glue: validate the PDF (client error -> 422), run the untested dots.ocr
# engine seam (render + vLLM, libs/dots_ocr/engine.py) off-thread under the lock to get per-page raw
# outputs, then hand each to the fully-tested DotsOcrPageNormalizer to produce the shared sidecar
# contract. Splitting the untested engine call from the tested normalization is what keeps this brick
# verifiable offline.

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio
import time
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.validation import InputValidator

# ====== Local Project Imports ======
from .engine import DotsOcrEngine
from .normalizer import DotsOcrPageNormalizer


class DotsOcrService(LoggerClass):
    """
    Manages the lifecycle of the dots.ocr VLM parse pipeline behind a serialized predict lock.

    The heavy vLLM model is loaded lazily by the engine on the first parse_pdf() call; this service
    only guards concurrency + validation and adapts the engine's per-page raw outputs into the
    sidecar's `{pages, n_pages, engine}` contract.
    """

    def __init__(
        self,
        model_path: str,
        render_dpi: int,
        max_pages: int,
        max_tokens: int,
        lock_wait_timeout_seconds: float,
    ) -> None:
        """
        Args:
            model_path (str): The dots.ocr model id/path forwarded to the engine.
            render_dpi (int): DPI each PDF page is rasterised to before inference.
            max_pages (int): Hard ceiling on pages parsed from one PDF (0 = no cap).
            max_tokens (int): Max new tokens the VLM may emit per page.
            lock_wait_timeout_seconds (float): Max seconds a parse_pdf() call waits for the predict
                lock before raising TimeoutError (-> HTTP 503).
        """
        LoggerClass.__init__(self)
        self._engine = DotsOcrEngine(
            model_path=model_path,
            render_dpi=render_dpi,
            max_pages=max_pages,
            max_tokens=max_tokens,
        )
        self._lock_wait_timeout_seconds = lock_wait_timeout_seconds
        # Serializes every analyze() call — dots.ocr VLM inference is not concurrency-safe on one GPU.
        self._lock = asyncio.Lock()

    @property
    def model_path(self) -> str:
        """The dots.ocr model id/path (surfaced in the boot log)."""
        return self._engine.model_path

    @property
    def ready(self) -> bool:
        """
        Returns:
            bool: Always True — the model loads lazily on the first parse and this service is not part
                of the readiness gate for model load (only the GPU gate in /health blocks readiness).
                Kept as a property for symmetry with the sibling sidecar services.
        """
        return True

    def unload(self) -> None:
        """Release the engine's model reference so the GC can reclaim GPU memory."""
        self._engine.unload()
        self.logger.info(f"dots.ocr pipeline unloaded")

    async def parse_pdf(self, pdf_bytes: bytes) -> dict[str, Any]:
        """
        Parse a PDF's bytes into the shared `{pages, n_pages, engine}` sidecar contract.

        Steps:
          1. Reject an undecodable PDF as a client error (HTTP 422) before spending inference.
          2. Acquire the shared predict lock (bounded wait -> TimeoutError -> HTTP 503).
          3. Run the dots.ocr engine off the event loop to get per-page raw outputs + page count.
          4. Normalize each page's raw output into the shared per-page contract.

        Args:
            pdf_bytes (bytes): Raw PDF content (the request body).

        Returns:
            dict[str, Any]: `{"pages": [...], "n_pages": int, "engine": {...}}`.

        Raises:
            InvalidInputError: If the body is not a decodable PDF (a client error -> HTTP 422).
            TimeoutError: If the predict lock cannot be acquired within the configured timeout.
        """
        # 1. Reject an undecodable PDF as a client error BEFORE spending inference.
        InputValidator.verify_pdf(pdf_bytes)

        # 2. Bounded wait on the shared predict lock — piling up behind a slow VLM parse would exhaust
        #    GPU memory; a timeout surfaces as a clear 503 instead.
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=self._lock_wait_timeout_seconds)
        except TimeoutError as exc:
            raise TimeoutError(
                f"Timed out after {self._lock_wait_timeout_seconds}s waiting for the dots.ocr predict "
                f"lock — the service is busy."
            ) from exc

        try:
            # 3. Run the (heavy, GPU-only) render + vLLM engine off the event loop.
            t0 = time.perf_counter()
            page_outputs, n_pages = await asyncio.to_thread(self._engine.analyze, pdf_bytes)
            elapsed = time.perf_counter() - t0
        finally:
            self._lock.release()

        # 4. Normalize each page's raw model output into the shared per-page contract (pure, tested).
        pages = [
            DotsOcrPageNormalizer.to_page(
                page_index=item["page_index"],
                image_width=item["image_width"],
                image_height=item["image_height"],
                raw_output=item["raw_output"],
            )
            for item in page_outputs
        ]
        effective_pages = n_pages or len(pages)
        self.logger.info(
            f"Parsed PDF ({len(pdf_bytes)} bytes) -> {len(pages)} pages in {elapsed:.1f}s "
            f"(dots.ocr {self.model_path})"
        )

        return {
            "pages": pages,
            "n_pages": effective_pages,
            "engine": {
                "dots_ocr": self._vllm_version(),
                "model": self.model_path,
                "backend": "vllm",
            },
        }

    @staticmethod
    def _vllm_version() -> str:
        """
        Best-effort installed vllm version string for the response's engine block.

        Returns:
            str: `vllm.__version__`, or "unknown" if the attribute/package is unavailable.
        """
        try:
            import vllm  # noqa: PLC0415

            return str(getattr(vllm, "__version__", "unknown"))
        except Exception:  # noqa: BLE001 — this must never break a successful parse response
            return "unknown"


__all__ = ["DotsOcrService"]

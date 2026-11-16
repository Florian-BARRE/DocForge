# ====== Code Summary ======
# Owns the single dots.ocr per-element layout VLM parse pipeline — the same lock-serialized,
# off-event-loop predict discipline as mineru_server's MineruService. dots.ocr inference is heavy
# (GPU-only, minutes per multi-page document) and not safe to run concurrently on one GPU, so every
# parse_pdf() is serialized behind a single asyncio.Lock (concurrency 1) and the actual engine call
# runs inside asyncio.to_thread so it never blocks the event loop. A caller that cannot acquire the
# lock within lock_wait_timeout gets a TimeoutError -> HTTP 503.
#
# This service is PURE-ish glue: run the untested dots.ocr engine seam (render + transformers,
# libs/dots_ocr/engine.py) off-thread under the lock to get per-page raw outputs, then hand each to the
# fully-tested DotsOcrPageNormalizer to produce the shared sidecar contract. Splitting the untested
# engine call from the tested normalization is what keeps this brick verifiable offline. It is the
# model_server_core ModelService of the dots.ocr host: the model loads LAZILY on the first parse, so
# load() has nothing to build at startup. The PDF is validated (client error -> 422) by the route,
# through the core InputValidator, before it gets here.

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio
import time
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from model_server_core import ModelService

# ====== Local Project Imports ======
from .engine import DotsOcrEngine
from .normalizer import DotsOcrPageNormalizer


class DotsOcrService(ModelService, LoggerClass):
    """
    Manages the lifecycle of the dots.ocr VLM parse pipeline behind a serialized predict lock.

    The heavy transformers model is loaded lazily by the engine on the first parse_pdf() call; this
    service only guards concurrency and adapts the engine's per-page raw outputs into the
    sidecar's `{pages, n_pages, engine}` contract.
    """

    def __init__(
        self,
        model_path: str,
        model_cache_home: str,
        render_dpi: int,
        max_pages: int,
        max_tokens: int,
        image_factor: int,
        min_pixels: int,
        max_pixels: int,
        lock_wait_timeout_seconds: float,
    ) -> None:
        """
        Args:
            model_path (str): The dots.ocr model id/path forwarded to the engine.
            model_cache_home (str): Root under which the engine materialises the weights as a dot-free
                local dir (dots.ocr's repo id contains a '.', which breaks transformers' remote-code
                import) — forwarded to the engine.
            render_dpi (int): DPI each PDF page is rasterised to before the smart-resize.
            max_pages (int): Hard ceiling on pages parsed from one PDF (0 = no cap).
            max_tokens (int): Max new tokens the VLM may emit per page.
            image_factor (int): Qwen2-VL dimension granularity each resized side is a multiple of.
            min_pixels (int): Lower bound on the smart-resized pixel count.
            max_pixels (int): Upper bound on the smart-resized pixel count.
            lock_wait_timeout_seconds (float): Max seconds a parse_pdf() call waits for the predict
                lock before raising TimeoutError (-> HTTP 503).
        """
        LoggerClass.__init__(self)
        self._engine = DotsOcrEngine(
            model_path=model_path,
            model_cache_home=model_cache_home,
            render_dpi=render_dpi,
            max_pages=max_pages,
            max_tokens=max_tokens,
            image_factor=image_factor,
            min_pixels=min_pixels,
            max_pixels=max_pixels,
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
            bool: Always True — the model loads lazily on the first parse, so readiness is not gated
                on the model being built (only the GPU gate of the server, `health_blocker`, blocks it).
        """
        return True

    def load(self) -> None:
        """Nothing to build at startup: dots.ocr's VLM loads lazily inside the engine on the first parse."""
        self.logger.info(f"dots.ocr model {self.model_path} loads LAZILY on the first /parse")

    def unload(self) -> None:
        """Release the engine's model reference so the GC can reclaim GPU memory."""
        self._engine.unload()
        self.logger.info(f"dots.ocr pipeline unloaded")

    async def parse_pdf(self, pdf_bytes: bytes) -> dict[str, Any]:
        """
        Parse a PDF's bytes into the shared `{pages, n_pages, engine}` sidecar contract.

        Steps:
          1. Acquire the shared predict lock (bounded wait -> TimeoutError -> HTTP 503).
          2. Run the dots.ocr engine off the event loop to get per-page raw outputs + page count.
          3. Normalize each page's raw output into the shared per-page contract.

        Args:
            pdf_bytes (bytes): Raw PDF content (the request body), already validated as a PDF.

        Returns:
            dict[str, Any]: `{"pages": [...], "n_pages": int, "engine": {...}}`.

        Raises:
            TimeoutError: If the predict lock cannot be acquired within the configured timeout.
        """
        # 1. Bounded wait on the shared predict lock — piling up behind a slow VLM parse would exhaust
        #    GPU memory; a timeout surfaces as a clear 503 instead.
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=self._lock_wait_timeout_seconds)
        except TimeoutError as exc:
            raise TimeoutError(
                f"Timed out after {self._lock_wait_timeout_seconds}s waiting for the dots.ocr predict "
                f"lock — the service is busy."
            ) from exc

        try:
            # 2. Run the (heavy, GPU-only) render + transformers engine off the event loop.
            t0 = time.perf_counter()
            page_outputs, n_pages = await asyncio.to_thread(self._engine.analyze, pdf_bytes)
            elapsed = time.perf_counter() - t0
        finally:
            self._lock.release()

        # 3. Normalize each page's raw model output into the shared per-page contract (pure, tested).
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
                "dots_ocr": self._transformers_version(),
                "model": self.model_path,
                "backend": "transformers",
            },
        }

    @staticmethod
    def _transformers_version() -> str:
        """
        Best-effort installed transformers version string for the response's engine block.

        Returns:
            str: `transformers.__version__`, or "unknown" if the attribute/package is unavailable.
        """
        try:
            import transformers  # noqa: PLC0415

            return str(getattr(transformers, "__version__", "unknown"))
        except Exception:  # noqa: BLE001 — this must never break a successful parse response
            return "unknown"


__all__ = ["DotsOcrService"]

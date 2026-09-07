# ====== Code Summary ======
# Owns the single MinerU2.5-Pro VLM parse pipeline — the same lock-serialized, off-event-loop predict
# discipline as paddle_server's PaddleOcrVlService. MinerU's VLM backend is heavy (GPU-only, min 8 GB
# VRAM, minutes per document) and not safe to run concurrently on one GPU, so every parse_pdf() is
# serialized behind a single asyncio.Lock (concurrency 1) and the actual MinerU call runs inside
# asyncio.to_thread so it never blocks the event loop. A caller that cannot acquire the lock within
# lock_wait_timeout gets a TimeoutError -> HTTP 503.
#
# This service is PURE-ish glue: validate the PDF (client error -> 422), run the untested MinerU engine
# seam (libs/mineru/engine.py) off-thread under the lock to get a content_list, then hand it to the
# fully-tested MineruContentListNormalizer to produce the shared sidecar contract. Splitting the
# untested engine call from the tested normalization is what keeps this brick verifiable offline.

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
from .engine import MineruEngine
from .normalizer import MineruContentListNormalizer


class MineruService(LoggerClass):
    """
    Manages the lifecycle of the MinerU2.5-Pro VLM parse pipeline behind a serialized predict lock.

    The heavy MinerU model is loaded lazily by the engine on the first parse_pdf() call; this service
    only guards concurrency + validation and adapts the engine's content_list into the sidecar's
    `{pages, n_pages, engine}` contract.
    """

    # Pinned MinerU model id reported in the /parse response's engine block — the parse-output contract
    # is version-sensitive, so it is stated explicitly rather than floated.
    MODEL_ID = "MinerU2.5-Pro-2605-1.2B"

    def __init__(
        self,
        backend: str,
        lang: str,
        model_source: str,
        model_cache_home: str,
        lock_wait_timeout_seconds: float,
    ) -> None:
        """
        Args:
            backend (str): The MinerU VLM backend id forwarded to the engine.
            lang (str): The OCR/parse language hint forwarded to the engine.
            model_source (str): Weight hoster ("huggingface"/"modelscope") — log-only in the engine.
            model_cache_home (str): Model cache root — log-only in the engine (set by compose env).
            lock_wait_timeout_seconds (float): Max seconds a parse_pdf() call waits for the predict
                lock before raising TimeoutError (-> HTTP 503).
        """
        LoggerClass.__init__(self)
        self._engine = MineruEngine(
            backend=backend,
            lang=lang,
            model_source=model_source,
            model_cache_home=model_cache_home,
        )
        self._lock_wait_timeout_seconds = lock_wait_timeout_seconds
        # Serializes every analyze() call — MinerU VLM inference is not concurrency-safe on one GPU.
        self._lock = asyncio.Lock()

    @property
    def ready(self) -> bool:
        """
        Returns:
            bool: Always True — the model loads lazily on the first parse and this service is not part
                of the readiness gate for model load (only the GPU gate in /health blocks readiness).
                Kept as a property for symmetry with the paddle_server services.
        """
        return True

    def unload(self) -> None:
        """Release the engine's model reference so the GC can reclaim GPU memory."""
        self._engine.unload()
        self.logger.info(f"MinerU pipeline unloaded")

    async def parse_pdf(self, pdf_bytes: bytes) -> dict[str, Any]:
        """
        Parse a PDF's bytes into the shared `{pages, n_pages, engine}` sidecar contract.

        Steps:
          1. Reject an undecodable PDF as a client error (HTTP 422) before spending inference.
          2. Acquire the shared predict lock (bounded wait -> TimeoutError -> HTTP 503).
          3. Run the MinerU engine off the event loop to get its content_list + page count.
          4. Normalize the content_list into the shared per-page contract.

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
                f"Timed out after {self._lock_wait_timeout_seconds}s waiting for the MinerU predict "
                f"lock — the service is busy."
            ) from exc

        try:
            # 3. Run the (heavy, GPU-only) MinerU engine off the event loop.
            t0 = time.perf_counter()
            content_list, n_pages = await asyncio.to_thread(self._engine.analyze, pdf_bytes)
            elapsed = time.perf_counter() - t0
        finally:
            self._lock.release()

        # 4. Normalize the flat content_list into the shared per-page contract (pure, tested).
        pages = MineruContentListNormalizer.to_pages(content_list)
        # Prefer the page count MinerU reported; fall back to the number of pages the normalizer built.
        effective_pages = n_pages or len(pages)
        self.logger.info(
            f"Parsed PDF ({len(pdf_bytes)} bytes) -> {len(pages)} pages in {elapsed:.1f}s "
            f"(MinerU {self.MODEL_ID}, backend={self._engine.backend})"
        )

        return {
            "pages": pages,
            "n_pages": effective_pages,
            "engine": {
                "mineru": self._mineru_version(),
                "pipeline": self.MODEL_ID,
                "backend": self._engine.backend,
            },
        }

    @staticmethod
    def _mineru_version() -> str:
        """
        Best-effort installed MinerU version string for the response's engine block.

        Returns:
            str: `mineru.__version__`, or "unknown" if the attribute/package is unavailable.
        """
        try:
            import mineru  # noqa: PLC0415

            return str(getattr(mineru, "__version__", "unknown"))
        except Exception:  # noqa: BLE001 — this must never break a successful parse response
            return "unknown"


__all__ = ["MineruService"]

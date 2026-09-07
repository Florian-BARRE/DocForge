# ====== Code Summary ======
# Owns the single PaddleOCR-VL 1.6 pipeline instance — the SAME lock-serialized, off-event-loop
# predict discipline as PpStructureService, with ONE deliberate difference: the pipeline is LAZILY
# built on the first /vl-parse request (behind an init lock), NOT at lifespan startup. PaddleOCR-VL is
# a heavy VLM (PP-DocLayoutV3 + PaddleOCR-VL-1.6-0.9B, ~9 GB peak, minutes to download on first run);
# building it eagerly would make every deployment pay that cost even though this parser is an
# OFF-by-default escalation head. Deferring it keeps the default PP-Structure users cheap: the model
# only materializes for a collection that actually wires the paddleocr_vl parser.
#
# Concurrency: PaddlePaddle inference is NOT thread-safe and PaddleOCR-VL peaks near ~9 GB per page,
# so every parse_pdf() call is serialized behind a single asyncio.Lock (concurrency 1) and the
# predict() call itself runs inside asyncio.to_thread so it never blocks the event loop. A caller that
# cannot acquire the lock within lock_wait_timeout gets a TimeoutError -> HTTP 503.

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
from .normalizer import PaddleOcrVlResponseNormalizer

# TYPE_CHECKING guard keeps the paddleocr/paddlex/paddlepaddle import out of the module's top-level
# scope; the actual import happens inside build() on the first request.
if TYPE_CHECKING:
    from paddleocr import PaddleOCRVL


class PaddleOcrVlService(LoggerClass):
    """
    Manages the lifecycle of the PaddleOCR-VL 1.6 layout-parsing pipeline.

    Unlike PpStructureService, the pipeline is built LAZILY on the first parse_pdf() call (behind an
    init lock) rather than at startup — see the module docstring. Sub-pipeline toggles passed here are
    the pipeline-level defaults (all heavy sub-pipelines OFF); a caller of parse_pdf() may override any
    per-request via PaddleX's predict() call-time override mechanism.
    """

    # Pinned PaddleOCR-VL pipeline version — the parse-output contract is version-sensitive, so it is
    # fixed here (not floated) and reported in the /vl-parse response's engine block.
    PIPELINE_VERSION = "v1.6"

    def __init__(
        self,
        use_chart_recognition: bool,
        use_seal_recognition: bool,
        use_ocr_for_image_block: bool,
        model_cache_home: str,
        model_source: str,
        lock_wait_timeout_seconds: float,
    ) -> None:
        """
        Args:
            use_chart_recognition (bool): Pipeline default for chart recognition (OFF — heavy).
            use_seal_recognition (bool): Pipeline default for seal recognition (OFF — not mapped).
            use_ocr_for_image_block (bool): Pipeline default for OCR-ing image blocks (OFF — figures
                are cropped by the DocForge figure_render stage, not OCR-ed inline here).
            model_cache_home (str): PADDLE_PDX_CACHE_HOME — set as an env var BEFORE this process
                starts (docker compose), not applied here; kept only for the boot log.
            model_source (str): PADDLE_PDX_MODEL_SOURCE — same as above, log-only.
            lock_wait_timeout_seconds (float): Max seconds a parse_pdf() call waits to acquire the
                shared predict lock before raising TimeoutError (-> HTTP 503).
        """
        LoggerClass.__init__(self)
        self._use_chart_recognition = use_chart_recognition
        self._use_seal_recognition = use_seal_recognition
        self._use_ocr_for_image_block = use_ocr_for_image_block
        self._model_cache_home = model_cache_home
        self._model_source = model_source
        self._lock_wait_timeout_seconds = lock_wait_timeout_seconds

        # Serializes every predict() call — PaddlePaddle is not thread-safe + ~9 GB peak per page.
        self._lock = asyncio.Lock()
        # Serializes the one-time lazy build so two concurrent first requests don't both construct it.
        self._build_lock = asyncio.Lock()
        # Typed attribute set by the lazy build(); None until the first /vl-parse request.
        self._pipeline: PaddleOCRVL | None = None

    # ── Properties ────────────────────────────────────────────────────────────────

    @property
    def ready(self) -> bool:
        """
        Returns:
            bool: True once the pipeline has been lazily built. False before the first request —
                this service is DELIBERATELY not part of the /health readiness gate (it is
                built-on-demand), so a False here never keeps the sidecar from serving.
        """
        return self._pipeline is not None

    # ── Public methods ─────────────────────────────────────────────────────────────

    def unload(self) -> None:
        """Release the pipeline reference so the GC can reclaim its (large) memory."""
        self._pipeline = None
        self.logger.info(f"PaddleOCR-VL pipeline unloaded")

    async def parse_pdf(
        self,
        pdf_bytes: bytes,
        *,
        use_chart_recognition: bool | None = None,
        use_seal_recognition: bool | None = None,
        use_ocr_for_image_block: bool | None = None,
    ) -> dict[str, Any]:
        """
        Parse a PDF's bytes into the shared `{pages, n_pages, engine}` sidecar contract.

        Steps mirror PpStructureService.parse_pdf, with a lazy build() up front:
          0. Lazily build the pipeline on the first call (behind the init lock).
          1. Reject an undecodable PDF as a client error (HTTP 422) before spending inference.
          2. Acquire the shared predict lock (bounded wait -> TimeoutError -> HTTP 503).
          3. Write the bytes to a temp file (PaddleX predict() takes a path) and run predict() off
             the event loop.
          4. Normalize each page result via PaddleOcrVlResponseNormalizer.
          5. Always clean up the temp file, even on failure.

        Args:
            pdf_bytes (bytes): Raw PDF content (the request body).
            use_chart_recognition (bool | None): Per-request override of the pipeline default.
            use_seal_recognition (bool | None): Per-request override of the pipeline default.
            use_ocr_for_image_block (bool | None): Per-request override of the pipeline default.

        Returns:
            dict[str, Any]: `{"pages": [...], "n_pages": int, "engine": {...}}`.

        Raises:
            InvalidInputError: If the body is not a decodable PDF (a client error -> HTTP 422).
            TimeoutError: If the predict lock cannot be acquired within the configured timeout.
        """
        # 0. Lazily build the pipeline on the first request (heavy model download/load).
        await self._ensure_built()

        # 1. Reject an undecodable PDF as a client error BEFORE spending inference.
        InputValidator.verify_pdf(pdf_bytes)

        # 2. Bounded wait on the shared predict lock — piling up behind a slow VLM predict() would
        #    exhaust memory; a timeout surfaces as a clear 503 instead.
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=self._lock_wait_timeout_seconds)
        except TimeoutError as exc:
            raise TimeoutError(
                f"Timed out after {self._lock_wait_timeout_seconds}s waiting for the "
                f"PaddleOCR-VL predict lock — the service is busy."
            ) from exc

        try:
            # 3. Materialize the PDF to a temp file for PaddleX's path-based predict() input.
            fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(pdf_bytes)

                t0 = time.perf_counter()
                results = await asyncio.to_thread(
                    self._predict_sync,
                    tmp_path,
                    {
                        "use_chart_recognition": use_chart_recognition,
                        "use_seal_recognition": use_seal_recognition,
                        "use_ocr_for_image_block": use_ocr_for_image_block,
                    },
                )
                elapsed = time.perf_counter() - t0
            finally:
                # 5. Always clean up the temp file, even on a predict() failure.
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        finally:
            self._lock.release()

        # 4. Normalize every page result into the shared sidecar contract.
        pages = [
            PaddleOcrVlResponseNormalizer.to_page(res, fallback_page_index=i)
            for i, res in enumerate(results)
        ]
        self.logger.info(
            f"Parsed PDF ({len(pdf_bytes)} bytes) -> {len(pages)} pages in {elapsed:.1f}s "
            f"(PaddleOCR-VL {self.PIPELINE_VERSION})"
        )

        return {
            "pages": pages,
            "n_pages": len(pages),
            "engine": {
                "paddleocr": self._paddleocr_version(),
                "pipeline": f"PaddleOCR-VL-{self.PIPELINE_VERSION}",
                # Report the EFFECTIVE settings PaddleX actually ran (per-request overrides applied),
                # read off the first result's model_settings — same discipline as PpStructureService.
                "sub_pipelines": self._model_settings(results),
            },
        }

    @staticmethod
    def _model_settings(results: list[Any]) -> dict[str, Any]:
        """
        Extract the effective `model_settings` PaddleX ran with, from the first page result.

        Args:
            results (list[Any]): The predict() result envelopes (mapping-like PaddleOCRVLResult).

        Returns:
            dict[str, Any]: The first result's model_settings, or {} when unavailable.
        """
        if not results:
            return {}
        first = results[0]
        try:
            settings = first["model_settings"]
        except (KeyError, TypeError, IndexError):
            settings = getattr(first, "model_settings", None)
        return dict(settings) if isinstance(settings, dict) else {}

    async def _ensure_built(self) -> None:
        """
        Build the PaddleOCR-VL pipeline on the first call; a no-op once built.

        The build runs behind a dedicated init lock so two concurrent first requests do not both
        construct the (heavy) pipeline. The predict() itself is guarded separately by self._lock.
        """
        if self._pipeline is not None:
            return
        async with self._build_lock:
            if self._pipeline is not None:  # another coroutine built it while we waited
                return
            await asyncio.to_thread(self._build_sync)

    def _build_sync(self) -> None:
        """
        Construct the PaddleOCRVL pipeline (synchronous, heavy) — runs inside asyncio.to_thread.

        Deferred here (not at import, not at lifespan) so the model download/load only happens the
        first time a collection actually escalates to this parser.
        """
        # Defer the heavy paddleocr/paddlex/paddlepaddle import to this moment (first request).
        from paddleocr import PaddleOCRVL  # noqa: PLC0415

        self.logger.info(
            f"Building PaddleOCR-VL pipeline (version={self.PIPELINE_VERSION}): "
            f"chart={self._use_chart_recognition}, seal={self._use_seal_recognition}, "
            f"ocr_for_image_block={self._use_ocr_for_image_block}, "
            f"model_cache_home={self._model_cache_home}, model_source={self._model_source} "
            f"— first request pays the model download/load"
        )
        t0 = time.perf_counter()
        # NOTE: unlike PpStructureService, no `enable_mkldnn=False` is passed. That workaround exists
        # because PP-StructureV3's layout-detection model SIGABRTs on PaddlePaddle 3.x's oneDNN CPU
        # path; PaddleOCR-VL's layout path (PP-DocLayoutV3) does NOT hit it — the CPU de-risk AND the
        # live /vl-parse run both succeed with the bare constructor. PaddleOCRVL also does not expose
        # PPStructureV3's `enable_mkldnn` knob (a different pipeline class), so there is nothing to set.
        self._pipeline = PaddleOCRVL(pipeline_version=self.PIPELINE_VERSION)
        elapsed = time.perf_counter() - t0
        self.logger.info(f"PaddleOCR-VL pipeline built in {elapsed:.1f}s")

    def _predict_sync(self, pdf_path: str, overrides: dict[str, bool | None]) -> list[Any]:
        """
        Synchronous predict() call — runs inside asyncio.to_thread (never call from the event loop).

        A None override means "use the pipeline's default" (PaddleX's own convention), so None values
        are dropped before the call rather than forced False.

        Args:
            pdf_path (str): Path to the temp PDF file written by parse_pdf().
            overrides (dict[str, bool | None]): Per-request sub-pipeline overrides.

        Returns:
            list[Any]: One result envelope per page, in page order.
        """
        assert self._pipeline is not None  # noqa: S101 — guaranteed by _ensure_built in the caller
        effective = {
            "use_chart_recognition": self._use_chart_recognition,
            "use_seal_recognition": self._use_seal_recognition,
            "use_ocr_for_image_block": self._use_ocr_for_image_block,
        }
        effective.update({k: v for k, v in overrides.items() if v is not None})
        return list(self._pipeline.predict(pdf_path, **effective))

    @staticmethod
    def _paddleocr_version() -> str:
        """
        Best-effort installed paddleocr version string for the response's engine block.

        Returns:
            str: `paddleocr.__version__`, or "unknown" if the attribute is unavailable.
        """
        try:
            import paddleocr  # noqa: PLC0415

            return str(getattr(paddleocr, "__version__", "unknown"))
        except Exception:  # noqa: BLE001 — this must never break a successful parse response
            return "unknown"


__all__ = ["PaddleOcrVlService"]

# ====== Code Summary ======
# Owns the single PPStructureV3 pipeline instance. Built once inside `build()`, called exclusively
# from the FastAPI lifespan — routes access it through CONTEXT. The heavy paddleocr/paddlex import
# is deferred to `build()` so importing this module never triggers the ML stack.
#
# Concurrency: PaddlePaddle inference is NOT thread-safe, so every `parse_pdf()` call is
# serialized behind a single `asyncio.Lock` — the sole `predict()` call itself runs inside
# `asyncio.to_thread` so it never blocks the event loop (mirrors the docling `_convert_lock`
# discipline referenced in the research plan). A caller that cannot acquire the lock within
# `lock_wait_timeout` gets a `TimeoutError`, translated to HTTP 503 by the router.

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio
import os
import tempfile
import time
from typing import TYPE_CHECKING, Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .normalizer import PpStructureResponseNormalizer

# TYPE_CHECKING guard keeps the paddleocr/paddlex/paddlepaddle import out of the module's
# top-level scope; the actual import happens inside build() at boot time.
if TYPE_CHECKING:
    from paddleocr import PPStructureV3


class PpStructureService(LoggerClass):
    """
    Manages the lifecycle of the PP-StructureV3 layout-parsing pipeline.

    The pipeline is built once during FastAPI startup (via `build()`) and torn down at shutdown
    (via `unload()`). Sub-pipeline toggles set here are the PIPELINE-LEVEL defaults; a caller of
    `parse_pdf()` may override any of them per-request (PaddleX's own `predict()` call-time
    override mechanism) EXCEPT `use_doc_unwarping`, which is always forced False (never accepted
    from a caller) per the DocForge provenance-normalization invariant.
    """

    def __init__(
        self,
        use_table_recognition: bool,
        use_formula_recognition: bool,
        use_seal_recognition: bool,
        use_doc_orientation_classify: bool,
        model_cache_home: str,
        model_source: str,
        lock_wait_timeout_seconds: float,
    ) -> None:
        """
        Args:
            use_table_recognition (bool): PADDLE_USE_TABLE_RECOGNITION — pipeline default.
            use_formula_recognition (bool): PADDLE_USE_FORMULA_RECOGNITION — pipeline default.
            use_seal_recognition (bool): PADDLE_USE_SEAL_RECOGNITION — pipeline default.
            use_doc_orientation_classify (bool): PADDLE_USE_DOC_ORIENTATION_CLASSIFY — default.
            model_cache_home (str): PADDLE_PDX_CACHE_HOME — set as an env var BEFORE this
                process starts (docker compose), not applied here; kept only for the boot log.
            model_source (str): PADDLE_PDX_MODEL_SOURCE — same as above, log-only.
            lock_wait_timeout_seconds (float): Max seconds a `parse_pdf()` call waits to acquire
                the shared predict lock before raising `TimeoutError` (-> HTTP 503).
        """
        LoggerClass.__init__(self)
        self._use_table_recognition = use_table_recognition
        self._use_formula_recognition = use_formula_recognition
        self._use_seal_recognition = use_seal_recognition
        self._use_doc_orientation_classify = use_doc_orientation_classify
        self._model_cache_home = model_cache_home
        self._model_source = model_source
        self._lock_wait_timeout_seconds = lock_wait_timeout_seconds

        # Serializes every predict() call — PaddlePaddle is not thread-safe (module docstring).
        self._lock = asyncio.Lock()
        # Typed attribute set by build(); None until the service is started.
        self._pipeline: PPStructureV3 | None = None

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
        Construct the PPStructureV3 pipeline with the configured sub-pipeline defaults.

        `use_doc_unwarping=False` is passed unconditionally — never a knob, per the DocForge
        provenance invariant (bbox normalization assumes the layout-detection image is the raw
        rendered page, not a geometrically unwarped one).
        """
        # Defer the heavy paddleocr/paddlex/paddlepaddle import to this moment — the container
        # is booting, matches bge_server's deferred-FlagEmbedding-import discipline.
        from paddleocr import PPStructureV3  # noqa: PLC0415

        self.logger.info(
            f"Building PPStructureV3 pipeline: table={self._use_table_recognition}, "
            f"formula={self._use_formula_recognition}, seal={self._use_seal_recognition}, "
            f"doc_orientation_classify={self._use_doc_orientation_classify}, "
            f"doc_unwarping=False (always), "
            f"model_cache_home={self._model_cache_home}, model_source={self._model_source}"
        )
        t0 = time.perf_counter()
        self._pipeline = PPStructureV3(
            use_table_recognition=self._use_table_recognition,
            use_formula_recognition=self._use_formula_recognition,
            use_seal_recognition=self._use_seal_recognition,
            use_doc_orientation_classify=self._use_doc_orientation_classify,
            use_doc_unwarping=False,
            # Disable oneDNN/MKLDNN: PaddlePaddle 3.x's PIR executor raises
            # "ConvertPirAttribute2RuntimeAttribute not support" on the layout-detection model's
            # oneDNN path on CPU. Forcing the native CPU kernels avoids it; harmless on GPU
            # (which never uses oneDNN). Verified: predict() succeeds with this off.
            enable_mkldnn=False,
        )
        elapsed = time.perf_counter() - t0
        self.logger.info(f"PPStructureV3 pipeline built in {elapsed:.1f}s")

    def unload(self) -> None:
        """Release the pipeline reference so the GC can reclaim its memory."""
        self._pipeline = None
        self.logger.info(f"PPStructureV3 pipeline unloaded")

    async def parse_pdf(
        self,
        pdf_bytes: bytes,
        *,
        use_table_recognition: bool | None = None,
        use_formula_recognition: bool | None = None,
        use_seal_recognition: bool | None = None,
        use_doc_orientation_classify: bool | None = None,
    ) -> dict[str, Any]:
        """
        Parse a PDF's bytes into the sidecar's `POST /layout-parsing` response contract.

        Steps:
          1. Acquire the shared predict lock (bounded wait -> TimeoutError -> HTTP 503).
          2. Write the PDF bytes to a temp file — PaddleX's `predict()` takes a path (or a
             directory / numpy array), not raw bytes; it renders + iterates pages internally.
          3. Run `predict()` in a worker thread (CPU/GPU-bound, must not block the event loop).
          4. Normalize each page result via `PpStructureResponseNormalizer`.
          5. Always clean up the temp file, even on failure.

        Args:
            pdf_bytes (bytes): Raw PDF content (the request body).
            use_table_recognition (bool | None): Per-request override of the pipeline default.
            use_formula_recognition (bool | None): Per-request override of the pipeline default.
            use_seal_recognition (bool | None): Per-request override of the pipeline default.
            use_doc_orientation_classify (bool | None): Per-request override of the default.

        Returns:
            dict[str, Any]: `{"pages": [...], "n_pages": int, "engine": {...}}`.

        Raises:
            RuntimeError: If `build()` has not been called yet.
            TimeoutError: If the predict lock cannot be acquired within the configured timeout.
        """
        if self._pipeline is None:
            raise RuntimeError(f"PpStructureService.build() has not been called yet.")

        # 1. Bounded wait on the shared lock — an unbounded wait would let requests pile up
        # forever behind one slow predict() call; a timeout surfaces as a clear 503 instead.
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=self._lock_wait_timeout_seconds)
        except TimeoutError as exc:
            raise TimeoutError(
                f"Timed out after {self._lock_wait_timeout_seconds}s waiting for the "
                f"PP-StructureV3 predict lock — the service is busy."
            ) from exc

        try:
            # 2. Materialize the PDF to a temp file for PaddleX's path-based predict() input.
            fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(pdf_bytes)

                # 3. Run the CPU/GPU-bound predict() call off the event loop.
                t0 = time.perf_counter()
                results = await asyncio.to_thread(
                    self._predict_sync,
                    tmp_path,
                    {
                        "use_table_recognition": use_table_recognition,
                        "use_formula_recognition": use_formula_recognition,
                        "use_seal_recognition": use_seal_recognition,
                        "use_doc_orientation_classify": use_doc_orientation_classify,
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

        # 4. Normalize every page result into the sidecar contract.
        pages = [
            PpStructureResponseNormalizer.to_page(res, fallback_page_index=i)
            for i, res in enumerate(results)
        ]
        self.logger.info(
            f"Parsed PDF ({len(pdf_bytes)} bytes) -> {len(pages)} pages in {elapsed:.1f}s"
        )

        model_settings = results[0].get("model_settings", {}) if results else {}
        return {
            "pages": pages,
            "n_pages": len(pages),
            "engine": {
                "paddleocr": self._paddleocr_version(),
                "pipeline": "PP-StructureV3",
                "sub_pipelines": dict(model_settings),
            },
        }

    def _predict_sync(self, pdf_path: str, overrides: dict[str, bool | None]) -> list[Any]:
        """
        Synchronous predict() call — runs inside `asyncio.to_thread` (never call directly from
        the event loop). `use_doc_unwarping=False` is hardcoded, never taken from `overrides`.

        Args:
            pdf_path (str): Path to the temp PDF file written by `parse_pdf()`.
            overrides (dict[str, bool | None]): Per-request sub-pipeline overrides; a None value
                means "use the pipeline's constructor default" (PaddleX's own convention).

        Returns:
            list[Any]: One dict-like result object per page, in page order.
        """
        assert self._pipeline is not None  # noqa: S101 — guarded by the caller
        return self._pipeline.predict(
            pdf_path,
            use_doc_unwarping=False,
            **overrides,
        )

    @staticmethod
    def _paddleocr_version() -> str:
        """
        Best-effort installed paddleocr version string for the response's `engine` block.

        Returns:
            str: `paddleocr.__version__`, or "unknown" if the attribute is unavailable.
        """
        try:
            import paddleocr  # noqa: PLC0415

            return str(getattr(paddleocr, "__version__", "unknown"))
        except Exception:  # noqa: BLE001 — this must never break a successful parse response
            return "unknown"

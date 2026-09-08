# ====== Code Summary ======
# The ONE GPU-only, GPU-UNTESTED seam of this sidecar: the thin wrapper that actually invokes MinerU's
# VLM backend on a PDF and returns its `content_list.json` payload (a flat list of blocks). Everything
# ELSE in this service is pure and unit-tested against a canned content_list fixture — this class is
# the boundary where the real MinerU2.5-Pro VLM model runs, which requires CUDA and cannot run on this
# CPU-only dev VM. It is deliberately kept minimal and file-based (it calls MinerU's own `do_parse`,
# then reads the `*_content_list.json` it writes) because that content_list format is MinerU's stable,
# documented output contract, far less prone to internal-API drift than reaching into MinerU's
# analyze/middle-json internals.
#
# GPU FIRST-DEPLOY VALIDATION (do this on the first GPU deploy, it could NOT be tested here):
#   * confirm the `do_parse(...)` call signature + kwargs match the installed MinerU version (2.5.x);
#   * confirm MINERU_BACKEND ("vlm-transformers" by default) loads MinerU2.5-Pro-2605-1.2B on CUDA;
#   * confirm the written output path glob `**/*_content_list.json` resolves to exactly one file;
#   * confirm the content_list block schema matches libs/mineru/normalizer.py's expectations.

# ====== Standard Library Imports ======
from __future__ import annotations

import json
import pathlib
import tempfile
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass


class MineruEngine(LoggerClass):
    """
    Runs a PDF through MinerU's VLM backend and returns its content_list payload.

    Instantiated once and reused; MinerU manages its own model singleton internally, so the first
    `analyze()` call pays the model download/load and subsequent calls reuse the warm model. Never
    thread-safe — the caller (MineruService) serializes every `analyze()` behind a lock and runs it off
    the event loop.
    """

    def __init__(self, backend: str, lang: str, model_source: str, model_cache_home: str) -> None:
        """
        Args:
            backend (str): The MinerU VLM backend id (e.g. "vlm-transformers", "vlm-vllm-engine").
            lang (str): The OCR/parse language hint forwarded to MinerU.
            model_source (str): "huggingface" or "modelscope" — the weight hoster (log-only; MinerU
                reads MINERU_MODEL_SOURCE from the environment itself).
            model_cache_home (str): The model cache root (log-only; set as an env var by compose).
        """
        LoggerClass.__init__(self)
        self._backend = backend
        self._lang = lang
        self._model_source = model_source
        self._model_cache_home = model_cache_home
        self._warmed = False

    @property
    def warmed(self) -> bool:
        """True once at least one analyze() has completed (the model is loaded)."""
        return self._warmed

    @property
    def backend(self) -> str:
        """The MinerU VLM backend id this engine runs (reported in the response's engine block)."""
        return self._backend

    def analyze(self, pdf_bytes: bytes) -> tuple[list[dict[str, Any]], int]:
        """
        Parse a PDF's bytes with MinerU's VLM backend and return (content_list, n_pages).

        Synchronous and heavy (GPU inference) — the caller MUST run this inside asyncio.to_thread and
        behind the predict lock. The first call additionally downloads/loads the model.

        Args:
            pdf_bytes (bytes): Raw PDF content.

        Returns:
            tuple[list[dict[str, Any]], int]: The MinerU content_list blocks and the PDF page count.

        Raises:
            RuntimeError: If MinerU produced no content_list output (an unexpected engine failure).
        """
        # 1. Defer the heavy MinerU/torch import to the first real parse (never at module import), so
        #    the module stays importable — and the normalizer stays unit-testable — without MinerU/CUDA.
        from mineru.cli.common import do_parse, read_fn  # noqa: PLC0415

        # 2. Run MinerU into an isolated temp output dir; it writes `<name>_content_list.json` there.
        with tempfile.TemporaryDirectory() as work_dir:
            pdf_path = pathlib.Path(work_dir) / "input.pdf"
            pdf_path.write_bytes(pdf_bytes)
            out_dir = pathlib.Path(work_dir) / "out"
            out_dir.mkdir(parents=True, exist_ok=True)

            # read_fn normalizes the PDF bytes the way MinerU's own CLI does before parsing.
            pdf_data = read_fn(pdf_path)
            do_parse(
                output_dir=str(out_dir),
                pdf_file_names=["input"],
                pdf_bytes_list=[pdf_data],
                p_lang_list=[self._lang],
                backend=self._backend,
                f_dump_content_list=True,
                f_dump_md=False,
                f_dump_middle_json=False,
                f_dump_model_output=False,
                f_draw_layout_bbox=False,
                f_draw_span_bbox=False,
            )

            content_list = self.__read_content_list(out_dir)

        self._warmed = True
        n_pages = self.__page_count(content_list)
        self.logger.info(
            f"MinerU parsed {len(pdf_bytes)} bytes -> {len(content_list)} blocks across "
            f"{n_pages} page(s) (backend={self._backend})"
        )
        return content_list, n_pages

    @staticmethod
    def __read_content_list(out_dir: pathlib.Path) -> list[dict[str, Any]]:
        """Locate and load the single `*_content_list.json` MinerU wrote under the output dir."""
        matches = sorted(out_dir.glob("**/*_content_list.json"))
        if not matches:
            raise RuntimeError(
                "MinerU produced no *_content_list.json — the VLM parse failed or wrote nowhere "
                f"under {out_dir}"
            )
        payload = json.loads(matches[0].read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []

    @staticmethod
    def __page_count(content_list: list[dict[str, Any]]) -> int:
        """Derive the page count from the highest 0-based page_idx present (+1), or 0 when empty."""
        max_idx = -1
        for block in content_list:
            if isinstance(block, dict):
                try:
                    max_idx = max(max_idx, int(block.get("page_idx")))
                except (TypeError, ValueError):
                    continue
        return max_idx + 1

    def unload(self) -> None:
        """Best-effort release of MinerU's loaded model so the GC can reclaim GPU memory."""
        # MinerU owns its model singleton; there is no public teardown hook, so this only flips the
        # warmed flag. A full release happens on process exit. Kept for lifespan symmetry.
        self._warmed = False
        # Free CUDA cache if torch is loaded (a no-op when it never was, e.g. before the first parse).
        try:
            import torch  # noqa: PLC0415

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 — teardown must never raise
            pass


__all__ = ["MineruEngine"]

# ====== Code Summary ======
# The ONE GPU-only, GPU-UNTESTED seam of this sidecar: renders each PDF page to an image (pypdfium2),
# then runs the dots.ocr per-element layout VLM (rednote-hilab/dots.ocr) over those page images via
# vLLM's in-process offline engine, returning each page's raw JSON output (a list of layout elements).
# Everything ELSE in this service is pure and unit-tested against a canned JSON string — this class is
# the boundary where the real dots.ocr VLM runs, which requires CUDA and cannot run on this CPU-only
# dev VM. It sends an OpenAI-style chat message (page image + the `prompt_layout_all_en` layout prompt)
# and reads back the model's JSON string; the pure DotsOcrPageNormalizer turns that string into the
# shared per-page contract.
#
# GPU FIRST-DEPLOY VALIDATION (do this on the first GPU deploy, it could NOT be tested here):
#   * confirm the model id DOTS_OCR_MODEL_PATH (default "rednote-hilab/dots.ocr") + that vLLM >=0.11
#     loads it with trust_remote_code=True on the target CUDA GPU (Tesla V100 sm_70 → torch cu126);
#   * confirm `_PROMPT_LAYOUT_ALL_EN` matches the current dots.ocr model card's layout prompt verbatim;
#   * confirm `LLM.chat(...)` with an image_url data-URI message returns the per-page JSON string in
#     `outputs[i].outputs[0].text` for the installed vLLM version;
#   * confirm the element JSON schema ({category, bbox pixels, text, reading_order}) matches
#     DotsOcrPageNormalizer's expectations (watch its bbox-fallback warning in the logs).

# ====== Standard Library Imports ======
from __future__ import annotations

import base64
import io
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# The layout prompt dots.ocr expects for a full-page parse. It asks the model to return, for every
# layout element, its category + pixel bbox + text (HTML for tables, LaTeX for formulas) in reading
# order, as a JSON list. MUST be verified against the current model card on first GPU deploy — a prompt
# mismatch degrades the output silently (the normalizer's bbox-fallback warning is the tripwire).
_PROMPT_LAYOUT_ALL_EN = (
    "Please output the layout information from this document image, including each layout element's "
    "bounding box, its category, and the text content inside the box.\n\n"
    "1. Bounding box format: [x1, y1, x2, y2] in absolute pixel coordinates of this image.\n"
    "2. Layout categories: Caption, Footnote, Formula, List-item, Page-footer, Page-header, Picture, "
    "Section-header, Table, Text, Title.\n"
    "3. Text content: use HTML for a Table, LaTeX for a Formula, Markdown for other text elements, and "
    "omit the text for a Picture.\n"
    "4. Order the elements in natural reading order and include a 0-based reading_order for each.\n\n"
    "Output ONLY a JSON list of objects, each with keys: category, bbox, text, reading_order."
)


class DotsOcrEngine(LoggerClass):
    """
    Renders a PDF's pages and runs the dots.ocr layout VLM over them via vLLM, per page.

    Instantiated once and reused; the vLLM engine loads LAZILY on the first `analyze()` call (pays the
    model download/load once) and is reused after. Never thread-safe — the caller (DotsOcrService)
    serializes every `analyze()` behind a lock and runs it off the event loop.
    """

    def __init__(self, model_path: str, render_dpi: int, max_pages: int, max_tokens: int) -> None:
        """
        Args:
            model_path (str): HuggingFace id or local path of the dots.ocr weights vLLM loads.
            render_dpi (int): DPI each PDF page is rasterised to before inference.
            max_pages (int): Hard ceiling on pages parsed from one PDF (0 = no cap).
            max_tokens (int): Max new tokens the VLM may emit per page.
        """
        LoggerClass.__init__(self)
        self._model_path = model_path
        self._render_dpi = render_dpi
        self._max_pages = max_pages
        self._max_tokens = max_tokens
        self._llm: Any | None = None

    @property
    def model_path(self) -> str:
        """The dots.ocr model id/path this engine loads (reported in the response's engine block)."""
        return self._model_path

    @property
    def warmed(self) -> bool:
        """True once the vLLM engine has been loaded (the first analyze() paid the load cost)."""
        return self._llm is not None

    def analyze(self, pdf_bytes: bytes) -> tuple[list[dict[str, Any]], int]:
        """
        Render + parse a PDF's pages, returning (per-page raw outputs, page count).

        Synchronous and heavy (GPU inference) — the caller MUST run this inside asyncio.to_thread and
        behind the predict lock. The first call additionally downloads/loads the vLLM model.

        Args:
            pdf_bytes (bytes): Raw PDF content.

        Returns:
            tuple[list[dict[str, Any]], int]: One dict per page
                (`{page_index, image_width, image_height, raw_output}`) and the PDF page count.
        """
        # 1. Render every page to a PNG + capture its pixel dims (the bbox normalization divisor).
        pages = self._render_pages(pdf_bytes)
        n_pages = len(pages)
        if self._max_pages > 0 and n_pages > self._max_pages:
            self.logger.warning(
                f"PDF has {n_pages} pages; capping at DOTS_OCR_MAX_PAGES={self._max_pages}."
            )
            pages = pages[: self._max_pages]

        # 2. Lazy-load the vLLM engine, then run one chat conversation per page (batched).
        llm = self._ensure_model()
        conversations = [self._build_conversation(png) for _, png, _, _ in pages]
        raw_texts = self._chat(llm, conversations)

        # 3. Pair each page's rendered dims with its raw model output for the normalizer.
        results: list[dict[str, Any]] = []
        for (page_index, _, width, height), raw in zip(pages, raw_texts):
            results.append(
                {
                    "page_index": page_index,
                    "image_width": width,
                    "image_height": height,
                    "raw_output": raw,
                }
            )
        self.logger.info(
            f"dots.ocr parsed {len(pdf_bytes)} bytes -> {len(results)} page(s) "
            f"(model={self._model_path})"
        )
        return results, n_pages

    # ── Rendering (CPU, pypdfium2) ───────────────────────────────────────────────────

    def _render_pages(self, pdf_bytes: bytes) -> list[tuple[int, bytes, int, int]]:
        """
        Rasterise every PDF page to a PNG, returning (page_index, png_bytes, width_px, height_px).

        The rendered pixel width/height become the bbox normalization divisor the DocForge mapper uses,
        so they are captured here and flow through the contract unchanged.
        """
        import pypdfium2 as pdfium  # noqa: PLC0415

        # pypdfium2 renders at 72 DPI * scale, so scale = target_dpi / 72.
        scale = self._render_dpi / 72.0
        rendered: list[tuple[int, bytes, int, int]] = []
        document = pdfium.PdfDocument(pdf_bytes)
        try:
            for page_index in range(len(document)):
                page = document[page_index]
                bitmap = page.render(scale=scale)
                image = bitmap.to_pil()
                width, height = image.width, image.height
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                rendered.append((page_index, buffer.getvalue(), width, height))
        finally:
            document.close()
        return rendered

    # ── vLLM engine (GPU) ────────────────────────────────────────────────────────────

    def _ensure_model(self) -> Any:
        """Lazy-load the vLLM offline engine for the dots.ocr weights (first call only)."""
        if self._llm is None:
            from vllm import LLM  # noqa: PLC0415

            self.logger.info(f"Loading dots.ocr via vLLM: {self._model_path} (first parse) ...")
            # trust_remote_code: dots.ocr ships a custom HF model class vLLM must import.
            self._llm = LLM(model=self._model_path, trust_remote_code=True)
        return self._llm

    def _build_conversation(self, png_bytes: bytes) -> list[dict[str, Any]]:
        """Build a one-turn OpenAI-style chat: the page image (data URI) + the layout prompt."""
        image_b64 = base64.b64encode(png_bytes).decode("ascii")
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                    {"type": "text", "text": _PROMPT_LAYOUT_ALL_EN},
                ],
            }
        ]

    def _chat(self, llm: Any, conversations: list[list[dict[str, Any]]]) -> list[str]:
        """Run the batched chat and return each conversation's generated text (empty list if none)."""
        if not conversations:
            return []
        from vllm import SamplingParams  # noqa: PLC0415

        sampling = SamplingParams(temperature=0.0, max_tokens=self._max_tokens)
        outputs = llm.chat(conversations, sampling)
        return [output.outputs[0].text if output.outputs else "" for output in outputs]

    def unload(self) -> None:
        """Best-effort release of the vLLM engine so the GC can reclaim GPU memory."""
        self._llm = None
        # Free CUDA cache if torch is loaded (a no-op when it never was, e.g. before the first parse).
        try:
            import torch  # noqa: PLC0415

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 — teardown must never raise
            pass


__all__ = ["DotsOcrEngine"]

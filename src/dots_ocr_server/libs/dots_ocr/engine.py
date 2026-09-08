# ====== Code Summary ======
# The ONE GPU-only, GPU-UNTESTED seam of this sidecar: renders each PDF page to an image (pypdfium2),
# then runs the dots.ocr per-element layout VLM (rednote-hilab/dots.ocr) over those page images via
# HuggingFace `transformers` (AutoModelForCausalLM + AutoProcessor + model.generate), returning each
# page's raw JSON output (a list of layout elements). Everything ELSE in this service is pure and
# unit-tested against a canned JSON string — this class is the boundary where the real dots.ocr VLM
# runs, which requires CUDA and cannot run on this CPU-only dev VM. It builds a Qwen2-VL chat message
# (the smart-resized page image + the `prompt_layout_all_en` layout prompt) and reads back the model's
# JSON string; the pure DotsOcrPageNormalizer turns that string into the shared per-page contract.
#
# WHY transformers, not vLLM: the prod GPU is a Tesla V100 (Volta, sm_70). vLLM >=0.11 DROPPED Volta
# support (its kernels require sm_75+), so it cannot run on a V100. HuggingFace `transformers` on torch
# cu126 DOES support sm_70, giving the broadest GPU compatibility (sm_70 → modern). On the V100 the
# model is loaded in fp16 (torch.float16 — Volta has no bf16 tensor cores) with the SDPA attention
# backend (attn_implementation="sdpa"; NO flash-attn, which needs sm_80+). The render→smart_resize→
# prompt→parse→normalize pipeline, the /parse contract, and the mapper are all UNCHANGED — only how the
# model is loaded and called was swapped.
#
# GPU FIRST-DEPLOY VALIDATION (do this on the first GPU deploy, it could NOT be tested here):
#   * GPU GATE: confirm the transformers model LOADS on the V100 with torch_dtype=torch.float16 +
#     attn_implementation="sdpa" (fp16 + SDPA is the sm_70-safe combo — bf16/flash-attn would fault).
#   * GPU GATE: confirm returned bboxes land in the SMART_RESIZED frame the model actually saw (the
#     dims this engine reports as image_width/image_height), NOT the raw render — spot-check one crop
#     against its page. A wrong divisor uniformly mis-scales every crop (the #1 risk of this brick).
#     The processor is pinned to the SAME min/max pixel budget the sidecar pre-resized to, so its own
#     smart-resize is idempotent on our already-conforming dims and does not re-resize differently.
#   * confirm the model id DOTS_OCR_MODEL_PATH (default "rednote-hilab/dots.ocr") loads with
#     trust_remote_code=True under the pinned transformers on the target CUDA GPU (torch cu126);
#   * confirm `_PROMPT_LAYOUT_ALL_EN` matches the current dots.ocr model card's layout prompt verbatim;
#   * confirm the smart-resize knobs (factor/min_pixels/max_pixels) match the model card;
#   * confirm `qwen_vl_utils.process_vision_info` + `processor.apply_chat_template` + `model.generate`
#     return the per-page JSON string for the installed transformers version;
#   * confirm the element JSON schema ({category, bbox pixels, text, reading_order}) matches
#     DotsOcrPageNormalizer's expectations (watch its bbox-fallback warning in the logs).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .resize import SmartResize

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
    Renders a PDF's pages and runs the dots.ocr layout VLM over them via HuggingFace transformers.

    Instantiated once and reused; the model + processor load LAZILY on the first `analyze()` call (pays
    the model download/load once) and are reused after. Never thread-safe — the caller (DotsOcrService)
    serializes every `analyze()` behind a lock and runs it off the event loop. The model is loaded in
    fp16 with the SDPA attention backend so it runs on a Tesla V100 (sm_70), which vLLM no longer
    supports.
    """

    def __init__(
        self,
        model_path: str,
        render_dpi: int,
        max_pages: int,
        max_tokens: int,
        image_factor: int,
        min_pixels: int,
        max_pixels: int,
    ) -> None:
        """
        Args:
            model_path (str): HuggingFace id or local path of the dots.ocr weights transformers loads.
            render_dpi (int): DPI each PDF page is rasterised to before the smart-resize.
            max_pages (int): Hard ceiling on pages parsed from one PDF (0 = no cap).
            max_tokens (int): Max new tokens the VLM may emit per page.
            image_factor (int): Qwen2-VL dimension granularity (28) each resized side is a multiple of.
            min_pixels (int): Lower bound on the smart-resized pixel count.
            max_pixels (int): Upper bound on the smart-resized pixel count.
        """
        LoggerClass.__init__(self)
        self._model_path = model_path
        self._render_dpi = render_dpi
        self._max_pages = max_pages
        self._max_tokens = max_tokens
        self._image_factor = image_factor
        self._min_pixels = min_pixels
        self._max_pixels = max_pixels
        self._model: Any | None = None
        self._processor: Any | None = None

    @property
    def model_path(self) -> str:
        """The dots.ocr model id/path this engine loads (reported in the response's engine block)."""
        return self._model_path

    @property
    def warmed(self) -> bool:
        """True once the transformers model has been loaded (the first analyze() paid the load cost)."""
        return self._model is not None

    def analyze(self, pdf_bytes: bytes) -> tuple[list[dict[str, Any]], int]:
        """
        Render + parse a PDF's pages, returning (per-page raw outputs, page count).

        Synchronous and heavy (GPU inference) — the caller MUST run this inside asyncio.to_thread and
        behind the predict lock. The first call additionally downloads/loads the transformers model.

        Args:
            pdf_bytes (bytes): Raw PDF content.

        Returns:
            tuple[list[dict[str, Any]], int]: One dict per page
                (`{page_index, image_width, image_height, raw_output}`) and the PDF page count.
        """
        # 1. Render + smart-resize each page (capped BEFORE rendering so a runaway page count can't
        #    OOM), capturing the RESIZED pixel dims — the frame the model sees, hence the bbox divisor.
        pages, n_pages = self._render_pages(pdf_bytes)

        # 2. Lazy-load the model + processor, then run one generation per page (lock-serialized).
        self._ensure_model()
        raw_texts = [self._generate(image) for _, image, _, _ in pages]

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

    def _render_pages(self, pdf_bytes: bytes) -> tuple[list[tuple[int, Any, int, int]], int]:
        """
        Rasterise + smart-resize the PDF pages, returning (rendered pages, total page count).

        Each page is rendered at DOTS_OCR_RENDER_DPI, then smart-resized to the Qwen2-VL frame the
        model's vision encoder sees; those RESIZED width/height become the bbox normalization divisor
        the DocForge mapper uses, so they are captured here and flow through the contract. The resized
        PIL image is kept (not re-encoded to PNG) — it is fed directly to the transformers processor.
        Rendering STOPS at DOTS_OCR_MAX_PAGES (0 = no cap) so a runaway page count never rasterises
        unbounded.

        Returns:
            tuple[list[tuple[int, Any, int, int]], int]: The per-page
                (page_index, resized_pil_image, resized_width, resized_height), and the PDF's total
                page count.
        """
        import pypdfium2 as pdfium  # noqa: PLC0415

        # pypdfium2 renders at 72 DPI * scale, so scale = target_dpi / 72.
        scale = self._render_dpi / 72.0
        rendered: list[tuple[int, Any, int, int]] = []
        document = pdfium.PdfDocument(pdf_bytes)
        try:
            total_pages = len(document)
            limit = total_pages
            if self._max_pages > 0 and total_pages > self._max_pages:
                self.logger.warning(
                    f"PDF has {total_pages} pages; rendering only the first "
                    f"DOTS_OCR_MAX_PAGES={self._max_pages}."
                )
                limit = self._max_pages
            for page_index in range(limit):
                page = document[page_index]
                image = page.render(scale=scale).to_pil()
                # Smart-resize to the frame the model actually sees (multiple of factor, within the
                # pixel budget), so the bboxes it returns are measured against these exact dims.
                target_height, target_width = SmartResize.dims(
                    image.height,
                    image.width,
                    factor=self._image_factor,
                    min_pixels=self._min_pixels,
                    max_pixels=self._max_pixels,
                )
                image = image.resize((target_width, target_height)).convert("RGB")
                rendered.append((page_index, image, target_width, target_height))
        finally:
            document.close()
        return rendered, total_pages

    # ── transformers model (GPU) ───────────────────────────────────────────────────────

    def _ensure_model(self) -> None:
        """Lazy-load the transformers model + processor for the dots.ocr weights (first call only)."""
        if self._model is None:
            import torch  # noqa: PLC0415
            from transformers import AutoModelForCausalLM, AutoProcessor  # noqa: PLC0415

            self.logger.info(
                f"Loading dots.ocr via transformers: {self._model_path} (first parse) ..."
            )
            # trust_remote_code: dots.ocr ships a custom HF model class transformers must import.
            # torch_dtype=float16 + attn_implementation="sdpa": the sm_70-safe combo for a Tesla V100
            # (no bf16 tensor cores, no flash-attn kernels). device_map="cuda" places the whole 3B
            # model on the single visible GPU (never sharded — "auto" is not wanted for one small model).
            self._model = AutoModelForCausalLM.from_pretrained(
                self._model_path,
                trust_remote_code=True,
                torch_dtype=torch.float16,
                attn_implementation="sdpa",
                device_map="cuda",
            )
            self._model.eval()
            # Pin the SAME min/max pixel budget the sidecar smart-resized to, so the processor's own
            # smart-resize is idempotent on our already-conforming dims (it does not re-resize the page
            # to a different frame than the divisor this engine reports) — the two must agree or every
            # crop is mis-scaled.
            self._processor = AutoProcessor.from_pretrained(
                self._model_path,
                trust_remote_code=True,
                min_pixels=self._min_pixels,
                max_pixels=self._max_pixels,
            )

    def _generate(self, image: Any) -> str:
        """
        Run one dots.ocr generation over a single smart-resized page image and return the raw text.

        Builds the Qwen2-VL chat (the page image + the layout prompt), lets the processor apply the
        chat template + vision preprocessing, greedily decodes (do_sample=False — deterministic layout
        JSON), and returns the model's generated string for the pure normalizer to consume.

        Args:
            image (Any): The smart-resized PIL page image (already at the reported bbox-divisor dims).

        Returns:
            str: The model's raw generated text (a JSON list of layout elements), or "" if empty.
        """
        import torch  # noqa: PLC0415
        from qwen_vl_utils import process_vision_info  # noqa: PLC0415

        # 1. Build the one-turn chat: the page image (pinned to our pixel budget so the processor's
        #    smart-resize stays idempotent) + the layout prompt.
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": image,
                        "min_pixels": self._min_pixels,
                        "max_pixels": self._max_pixels,
                    },
                    {"type": "text", "text": _PROMPT_LAYOUT_ALL_EN},
                ],
            }
        ]

        # 2. Apply the chat template + vision preprocessing the model's own processor defines.
        prompt_text = self._processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self._processor(
            text=[prompt_text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(self._model.device)

        # 3. Greedy-decode the layout JSON, then trim the prompt tokens before decoding to text.
        with torch.inference_mode():
            generated = self._model.generate(
                **inputs, max_new_tokens=self._max_tokens, do_sample=False
            )
        trimmed = [out[len(inp):] for inp, out in zip(inputs.input_ids, generated)]
        decoded = self._processor.batch_decode(
            trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )
        return decoded[0] if decoded else ""

    def unload(self) -> None:
        """Best-effort release of the model + processor so the GC can reclaim GPU memory."""
        self._model = None
        self._processor = None
        # Free CUDA cache if torch is loaded (a no-op when it never was, e.g. before the first parse).
        try:
            import torch  # noqa: PLC0415

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 — teardown must never raise
            pass


__all__ = ["DotsOcrEngine"]

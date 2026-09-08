# ====== Code Summary ======
# Normalizes dots.ocr's per-page model output (a JSON STRING = a list of layout elements) into the SAME
# clean per-page block contract the mineru_server / paddle_server sidecars emit (see
# ../../backend/routers/parse/models.py). Producing an identical wire shape is deliberate: the DocForge
# IR mapper family (DotsOcrIRMapper) reuses the pp_structure span-aware table flattener + bbox
# normalization, so a shared contract means a shared mapper style — one place to maintain.
#
# What this module owns (all PURE, no transformers/torch import — unit-testable from a canned JSON string):
#   * JSON PARSING: the model returns a JSON string (optionally wrapped in a ```json fence); parse it
#     defensively into a list of elements, degrading a malformed page to an empty block list + a warning.
#   * CATEGORY -> CONTENT SLOT: dots.ocr emits `category` + `text`; Table's text is HTML, Formula's is
#     LaTeX, Picture has no text, everything else is Markdown/plain text. Route each into the contract's
#     html / latex / text slot. The DocForge mapper owns category->BlockType, so `label` is kept verbatim.
#   * BBOX: dots.ocr bboxes are `[x0, y0, x1, y1]` in the RENDERED page image's PIXEL space (top-left
#     origin). They are passed through as ints alongside the page's rendered pixel dims; the DocForge
#     mapper divides bbox by those dims to recover [0, 1]. A missing/malformed bbox degrades to the
#     full page — and if a HIGH fraction of a page's elements fall back that way, that is a schema-
#     mismatch signal (this brick is GPU-untested), so it is logged as a WARNING.
#   * READING ORDER: taken from each element's `reading_order`, falling back to list position.

# ====== Standard Library Imports ======
import json
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

logger = loggerplusplus.bind(identifier="DotsOcrNormalizer")

# dots.ocr categories whose `text` field is NOT plain text: a Table's text is an HTML table, a
# Formula's is LaTeX. Everything else (Text, Title, Section-header, List-item, Caption, Footnote,
# Page-header, Page-footer) carries Markdown/plain text; Picture carries no text at all.
_TABLE_CATEGORY = "table"
_FORMULA_CATEGORY = "formula"
_PICTURE_CATEGORY = "picture"

# When more than this fraction of a page's elements have a missing/malformed bbox, warn: on a real
# dots.ocr page every element carries a 4-number pixel bbox, so a high fallback rate means the model
# output schema drifted from what this normalizer expects (a GPU-untested-seam signal).
_BBOX_FALLBACK_WARN_RATIO = 0.5


class DotsOcrPageNormalizer:
    """
    Converts dots.ocr per-page model output (a JSON string) into the sidecar's per-page HTTP contract.

    Static-only helper (mirrors the sidecar's other static helpers) — never instantiated. Emits the
    SAME `{page_index, image_width, image_height, blocks:[{label, bbox, reading_order,
    text|html|latex}]}` page shape as the mineru_server/paddle_server normalizers so every layout-VLM
    sidecar shares one DocForge IR mapper style.
    """

    logger = logger

    def __new__(cls, *args: Any, **kwargs: Any) -> "DotsOcrPageNormalizer":
        raise TypeError(f"{cls.__name__} is static-only and must not be instantiated.")

    # ── Public API ─────────────────────────────────────────────────────────────────

    @classmethod
    def to_page(
        cls, page_index: int, image_width: int, image_height: int, raw_output: str
    ) -> dict[str, Any]:
        """
        Normalize one page's dots.ocr JSON output into a page contract dict.

        Args:
            page_index (int): 0-based page index within the PDF.
            image_width (int): Rendered page image width in pixels (the bbox x divisor downstream).
            image_height (int): Rendered page image height in pixels (the bbox y divisor downstream).
            raw_output (str): The model's raw response for this page — a JSON string listing layout
                elements (optionally wrapped in a ```json fence).

        Returns:
            dict[str, Any]: `{page_index, image_width, image_height, blocks}` (blocks in reading order).
        """
        # 1. Parse the model's JSON string into a list of elements (degrade a bad page to empty).
        elements = cls.__parse_elements(raw_output, page_index)

        # 2. Sort by the model's reading_order (fallback to list position), then map each element.
        ordered = sorted(
            enumerate(elements), key=lambda pair: cls.__int(pair[1].get("reading_order"), pair[0])
        )
        blocks: list[dict[str, Any]] = []
        bbox_fallbacks = 0
        for _, element in ordered:
            block, bbox_ok = cls.__to_block(element, image_width, image_height, len(blocks))
            if block is None:
                continue
            if not bbox_ok:
                bbox_fallbacks += 1
            blocks.append(block)

        # 3. A high bbox-fallback rate is a schema-mismatch signal (GPU-untested seam) — warn.
        if blocks and bbox_fallbacks / len(blocks) > _BBOX_FALLBACK_WARN_RATIO:
            cls.logger.warning(
                f"Page {page_index}: {bbox_fallbacks}/{len(blocks)} blocks fell back to a full-page "
                f"bbox — dots.ocr output schema may have drifted from the expected "
                f"{{category, bbox, text, reading_order}} element shape."
            )

        return {
            "page_index": page_index,
            "image_width": image_width,
            "image_height": image_height,
            "blocks": blocks,
        }

    # ── Element mapping ──────────────────────────────────────────────────────────────

    @classmethod
    def __to_block(
        cls, element: Any, image_width: int, image_height: int, reading_order: int
    ) -> tuple[dict[str, Any] | None, bool]:
        """
        Map one dots.ocr element into a contract block + whether its bbox was valid.

        Args:
            element (Any): One dots.ocr layout element (expected a dict with category/bbox/text).
            image_width (int): Rendered page width (for the full-page fallback bbox).
            image_height (int): Rendered page height (for the full-page fallback bbox).
            reading_order (int): 0-based position assigned to this block within the page.

        Returns:
            tuple[dict[str, Any] | None, bool]: The block dict (or None to skip a non-dict element),
                and True when the source bbox was a valid 4-number box (False when it fell back).
        """
        # 1. Skip an element that is not even a dict (malformed model output).
        if not isinstance(element, dict):
            return None, False

        category = str(element.get("category", "")).strip()
        bbox, bbox_ok = cls.__bbox(element.get("bbox"), image_width, image_height)

        block: dict[str, Any] = {
            "label": category,
            "bbox": bbox,
            "reading_order": reading_order,
        }

        # 2. Route the model `text` into the ONE content slot the category needs. Written as explicit
        #    branches (no dead ternary): Table -> html, Formula -> latex, Picture -> no text slot,
        #    everything else -> text.
        lowered = category.lower()
        text = element.get("text")
        text = str(text) if text is not None else ""
        if lowered == _TABLE_CATEGORY:
            block["html"] = text
        elif lowered == _FORMULA_CATEGORY:
            block["latex"] = text
        elif lowered == _PICTURE_CATEGORY:
            block["text"] = ""
        else:
            block["text"] = text
        return block, bbox_ok

    # ── bbox helpers ───────────────────────────────────────────────────────────────

    @classmethod
    def __bbox(cls, bbox: Any, image_width: int, image_height: int) -> tuple[list[int], bool]:
        """
        Coerce a dots.ocr pixel bbox to `[x0, y0, x1, y1]` ints, degrading to the full page.

        Args:
            bbox (Any): The element's `bbox` (expected [x0, y0, x1, y1] pixels).
            image_width (int): Rendered page width — the full-page fallback x extent.
            image_height (int): Rendered page height — the full-page fallback y extent.

        Returns:
            tuple[list[int], bool]: The pixel bbox and True when it was a valid 4-number box; the
                full-page box and False when it was missing/malformed.
        """
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return [0, 0, image_width, image_height], False
        try:
            return [int(round(float(value))) for value in bbox], True
        except (TypeError, ValueError):
            return [0, 0, image_width, image_height], False

    # ── JSON parsing ───────────────────────────────────────────────────────────────

    @classmethod
    def __parse_elements(cls, raw_output: str, page_index: int) -> list[Any]:
        """
        Parse the model's raw response string into a list of elements, degrading to [] on failure.

        Strips an optional ```json ... ``` markdown fence (VLMs frequently wrap JSON in one) before
        decoding. A non-list decode or a JSON error yields an empty page (logged) rather than a crash.
        """
        text = (raw_output or "").strip()
        if not text:
            return []

        # 1. Strip a leading/trailing markdown code fence if the model wrapped its JSON in one.
        if text.startswith("```"):
            text = text[3:]
            if text[:4].lower() == "json":
                text = text[4:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        # 2. Decode; a malformed page degrades to empty (with a warning) instead of failing the parse.
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            cls.logger.warning(f"Page {page_index}: dots.ocr output is not valid JSON ({exc}).")
            return []
        if not isinstance(parsed, list):
            cls.logger.warning(
                f"Page {page_index}: dots.ocr output decoded to {type(parsed).__name__}, "
                f"expected a list of elements."
            )
            return []
        # Keep only object elements: the model can emit a valid JSON array of non-objects
        # (e.g. `["heading","para"]`). Downstream sorts/maps assume dict elements, so drop the
        # rest HERE (with a warning) rather than let a `.get()` on a str/int raise mid-sort and
        # 500 the whole PDF — a malformed page degrades to its usable blocks, never a hard fail.
        elements = [element for element in parsed if isinstance(element, dict)]
        if len(elements) != len(parsed):
            cls.logger.warning(
                f"Page {page_index}: dropped {len(parsed) - len(elements)} non-object element(s) "
                f"from dots.ocr output (expected objects)."
            )
        return elements

    @staticmethod
    def __int(value: Any, default: int) -> int:
        """Coerce a value to int, falling back to `default` on anything non-numeric."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default


__all__ = ["DotsOcrPageNormalizer"]

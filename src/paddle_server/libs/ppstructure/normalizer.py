# ====== Code Summary ======
# Normalizes a raw PPStructureV3.predict() result (one `LayoutParsingResultV2`-like dict-like
# object per PDF page) into the sidecar's own clean, reading-ordered, joined-content contract
# (see PpStructureResponseNormalizer.to_page). Verified against the paddleocr==3.7.0 /
# paddlex==3.7.0 wheel source (docs do not spell this shape out — see revision.py):
#
# - `res["parsing_res_list"]` is a `List[LayoutBlock]` — NATIVE Python objects (`.label`,
#   `.content`, `.bbox`, `.order_index`), not a pre-serialized dict. Accessing it directly (NOT
#   via the `.json`/`.str` mixins, which additionally try to serialize doc_preprocessor_res /
#   layout_det_res / overall_ocr_res numpy images) is the cheapest, safest extraction path.
# - PaddleX ALREADY does the "messy join" internally before the block list is built
#   (paddlex.inference.pipelines.layout_parsing.pipeline_v2):
#     * table blocks   -> `block.content` = `table_res_list[i]["pred_html"]` (the HTML string)
#     * formula blocks -> formula results are folded into `overall_ocr_res` as OCR text entries
#       BEFORE the block loop (`convert_formula_res_to_ocr_format`), so `block.content` is the
#       raw `rec_formula` LaTeX string, unwrapped (no surrounding `$`).
#   So this sidecar's normalizer does NOT need to separately walk `table_res_list` /
#   `formula_res_list` and align them by bbox/region-id — `parsing_res_list` is already the
#   single clean per-page block list the DocForge mapper expects.
# - `res["width"]` / `res["height"]` are the pixel dims of the EXACT image layout detection ran
#   on (`doc_preprocessor_image.shape[:2]`) — i.e. the same pixel space as every `block.bbox` —
#   so no separate page-image render/measure step is needed on the sidecar side either.
#
# VERSION-DRIFT GUARD: PaddleOCR release/3.0 emitted a different, nested `parsing_res_list` shape
# (`{layout_bbox, "{label}": content, layout}` — label as a dynamic dict key). Since the pin above
# is exact (3.7.0, well past that shape), the object-attribute path below is not expected to ever
# hit the legacy dict form — but PpStructureResponseNormalizer._to_block still degrades such a block
# to a safe placeholder (label="", bbox=[0,0,0,0], text="") rather than crashing if a future pin
# bump changes the object shape again.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

logger = loggerplusplus.bind(identifier="PpStructureNormalizer")

# Labels whose recognized content is HTML (table structure), not plain text.
_HTML_LABELS = frozenset({"table"})
# Labels whose recognized content is LaTeX source, not plain text.
_LATEX_LABELS = frozenset({"formula"})


class PpStructureResponseNormalizer:
    """
    Converts raw PPStructureV3 per-page result objects into the sidecar's HTTP contract.

    Static-only helper (mirrors the DocForge `*ParseHelpers` convention) — never instantiated.
    """

    def __new__(cls, *args: Any, **kwargs: Any) -> "PpStructureResponseNormalizer":
        raise TypeError(f"{cls.__name__} is static-only and must not be instantiated.")

    @staticmethod
    def to_page(res: Any, fallback_page_index: int) -> dict[str, Any]:
        """
        Normalize one page result object into the sidecar's page contract.

        Args:
            res (Any): One element of `PPStructureV3.predict()`'s return list — a dict-like
                `LayoutParsingResultV2` result (supports `res["field"]` item access).
            fallback_page_index (int): Used when the result carries no `page_index` (e.g. a
                single-image input) — the 0-based position of this result in the predict() list.

        Returns:
            dict[str, Any]: `{"page_index", "image_width", "image_height", "blocks"}` — see the
                sidecar's `POST /layout-parsing` response contract in backend/routers.
        """
        # 1. Page-image pixel dims — the space every block bbox already lives in (module
        # docstring). Falls back to 0 defensively; a 0 divisor is caught client-side, never here.
        image_width = int(res["width"]) if res.get("width") is not None else 0
        image_height = int(res["height"]) if res.get("height") is not None else 0
        page_index = res["page_index"] if res.get("page_index") is not None else fallback_page_index

        # 2. Extract + reading-order-sort the block list (native LayoutBlock objects).
        raw_blocks = list(res["parsing_res_list"] or [])
        raw_blocks.sort(key=PpStructureResponseNormalizer._sort_key)

        # 3. Build the joined, typed block list.
        blocks = [
            PpStructureResponseNormalizer._to_block(block, reading_order)
            for reading_order, block in enumerate(raw_blocks)
        ]

        return {
            "page_index": int(page_index),
            "image_width": image_width,
            "image_height": image_height,
            "blocks": blocks,
        }

    @staticmethod
    def _sort_key(block: Any) -> int:
        """
        Reading-order sort key for one LayoutBlock — order_index when assigned, else index,
        else 0 (defensive: neither should ever be None on a fully-processed result, but a
        malformed/partial block must never crash the whole page).

        Args:
            block (Any): A `LayoutBlock`-like object (or defensively, a dict).

        Returns:
            int: The reading-order sort key.
        """
        order_index = PpStructureResponseNormalizer._get(block, "order_index")
        if order_index is not None:
            return int(order_index)
        index = PpStructureResponseNormalizer._get(block, "index")
        return int(index) if index is not None else 0

    @staticmethod
    def _to_block(block: Any, reading_order: int) -> dict[str, Any]:
        """
        Convert one LayoutBlock into the contract's block dict.

        Args:
            block (Any): A `LayoutBlock`-like object exposing `.label`, `.content`, `.bbox`
                (or the dict-shaped equivalent — defensive fallback, see module docstring).
            reading_order (int): This block's position in the already-sorted page block list.

        Returns:
            dict[str, Any]: `{"label", "bbox", "reading_order", <text|html|latex>}`.
        """
        label = str(PpStructureResponseNormalizer._get(block, "label") or "")
        bbox_raw = PpStructureResponseNormalizer._get(block, "bbox") or [0, 0, 0, 0]
        bbox = [int(v) for v in bbox_raw]
        content = PpStructureResponseNormalizer._get(block, "content")
        content = "" if content is None else str(content)

        out: dict[str, Any] = {"label": label, "bbox": bbox, "reading_order": reading_order}
        if label in _HTML_LABELS:
            out["html"] = content
        elif label in _LATEX_LABELS:
            out["latex"] = content
        else:
            out["text"] = content
        return out

    @staticmethod
    def _get(obj: Any, attr: str) -> Any:
        """
        Attribute-or-key access — the primary path is `LayoutBlock` objects (`.label`, `.bbox`,
        `.content`, `.order_index`, `.index`); the dict fallback only guards against a future
        PaddleX version reverting to a dict-shaped block (module docstring version-drift note).

        Args:
            obj (Any): A `LayoutBlock`-like object or a dict.
            attr (str): Attribute/key name to read.

        Returns:
            Any: The value, or None if present on neither shape.
        """
        if hasattr(obj, attr):
            return getattr(obj, attr)
        if isinstance(obj, dict):
            return obj.get(attr)
        return None

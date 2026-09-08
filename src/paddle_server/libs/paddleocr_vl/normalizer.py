# ====== Code Summary ======
# Normalizes a raw PaddleOCR-VL 1.6 predict() result (one native page envelope per PDF page) into the
# SAME clean, reading-ordered, joined-content contract the PP-StructureV3 sidecar emits (see
# backend/routers/layout_parsing/models.py). Producing an identical wire shape is deliberate: the
# DocForge IR mapper for paddleocr_vl reuses the pp_structure mapper's helpers, so a shared contract
# means a shared mapper — one place to maintain.
#
# What differs from the PP-StructureV3 normalizer is only the RAW per-block field names PaddleOCR-VL
# uses (`block_label` / `block_content` / `block_bbox` / `block_order`, not `.label` / `.content` /
# `.bbox` / `.order_index`) and the reading-order rule below. Verified against a real captured
# PaddleOCR-VL 1.6 sample (attention.pdf p8 with a rowspan table + multifig.pdf p0 with images):
#   * `parsing_res_list` is emitted ALREADY in visual reading order (its `block_id` is that monotonic
#     0-based index). `block_order` is only a PARTIAL signal — it is None on tables/figures/captions/
#     page-numbers — so re-sorting on it interleaves figures and captions out of place. List order is
#     therefore authoritative: reading_order = the block's position in parsing_res_list. (This is the
#     "fallback to list order" rule taken as the governing one, since block_order-when-None-inherits-
#     the-previous-order is provably equivalent to preserving list order on a monotonic list.)
#   * `block_content` is already the joined content: a `table` block carries the HTML string
#     (rowspan/colspan, LaTeX in cells), a `formula` block the raw LaTeX, an `image` block the empty
#     string, every text label its plain text — so no separate table_res / formula_res walk is needed.
#   * `width` / `height` are the pixel dims of the exact image layout detection ran on — the same
#     pixel space every `block_bbox` lives in — so the bbox divisor needs no separate page render.
#
# LIVE-SHAPE CONFIRMED (introspected inside the running container against the real predict() output):
# each result is a `PaddleOCRVLResult` that IS a mapping — `res["width"]` / `res["height"]` /
# `res["page_index"]` / `res["parsing_res_list"]` resolve directly, and the blocks are dicts keyed by
# `block_label` / `block_content` / `block_bbox` / `block_order`. (`res.json` also exists but nests the
# same payload one level down under a "res" key.) `_page_get` / `_get` below read the item-access path
# first, so the raw PaddleOCRVLResult is fed straight in — matching PpStructureResponseNormalizer.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

logger = loggerplusplus.bind(identifier="PaddleOcrVlNormalizer")

# Labels whose recognized content is HTML (table structure), not plain text.
_HTML_LABELS = frozenset({"table"})
# Labels whose recognized content is LaTeX source, not plain text.
_LATEX_LABELS = frozenset({"formula"})


class PaddleOcrVlResponseNormalizer:
    """
    Converts raw PaddleOCR-VL 1.6 per-page result envelopes into the sidecar's HTTP contract.

    Static-only helper (mirrors the DocForge `*ParseHelpers` convention) — never instantiated. Emits
    the SAME `{page_index, image_width, image_height, blocks:[{label, bbox, reading_order,
    text|html|latex}]}` page shape as PpStructureResponseNormalizer so both sidecars share one mapper.
    """

    def __new__(cls, *args: Any, **kwargs: Any) -> "PaddleOcrVlResponseNormalizer":
        raise TypeError(f"{cls.__name__} is static-only and must not be instantiated.")

    @staticmethod
    def to_page(res: Any, fallback_page_index: int) -> dict[str, Any]:
        """
        Normalize one PaddleOCR-VL page result into the sidecar's page contract.

        Args:
            res (Any): One element of `PaddleOCRVL.predict()`'s return list — a dict-like page
                envelope exposing `width` / `height` / `page_index` / `parsing_res_list`.
            fallback_page_index (int): Used when the envelope carries no `page_index` — the 0-based
                position of this result in the predict() list.

        Returns:
            dict[str, Any]: `{"page_index", "image_width", "image_height", "blocks"}` — the shared
                sidecar contract (see backend/routers/layout_parsing/models.py).
        """
        # 1. Page-image pixel dims — the space every block bbox already lives in. Falls back to 0
        #    defensively; a 0 divisor is caught client-side by the IR mapper, never here.
        width = PaddleOcrVlResponseNormalizer._page_get(res, "width")
        height = PaddleOcrVlResponseNormalizer._page_get(res, "height")
        image_width = int(width) if width is not None else 0
        image_height = int(height) if height is not None else 0
        page_index_raw = PaddleOcrVlResponseNormalizer._page_get(res, "page_index")
        page_index = int(page_index_raw) if page_index_raw is not None else fallback_page_index

        # 2. parsing_res_list is already in reading order (block_id == list position, see module
        #    docstring): preserve it and assign reading_order = the block's list position. A None
        #    block (defensive — a partial/degraded page) is skipped so it never crashes the page.
        raw_blocks = list(PaddleOcrVlResponseNormalizer._page_get(res, "parsing_res_list") or [])
        blocks = [
            PaddleOcrVlResponseNormalizer._to_block(block, reading_order)
            for reading_order, block in enumerate(b for b in raw_blocks if b is not None)
        ]

        return {
            "page_index": int(page_index),
            "image_width": image_width,
            "image_height": image_height,
            "blocks": blocks,
        }

    @staticmethod
    def _to_block(block: Any, reading_order: int) -> dict[str, Any]:
        """
        Convert one PaddleOCR-VL block into the contract's block dict.

        Args:
            block (Any): A raw block exposing `block_label` / `block_content` / `block_bbox` (dict
                keys in the captured sample, attributes on a native result object — both handled).
            reading_order (int): This block's 0-based position in the reading-ordered page list.

        Returns:
            dict[str, Any]: `{"label", "bbox", "reading_order", <text|html|latex>}`.
        """
        label = str(PaddleOcrVlResponseNormalizer._get(block, "block_label", "label") or "")
        bbox_raw = PaddleOcrVlResponseNormalizer._get(block, "block_bbox", "bbox") or [0, 0, 0, 0]
        bbox = [int(v) for v in bbox_raw]
        content = PaddleOcrVlResponseNormalizer._get(block, "block_content", "content")
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
    def _page_get(res: Any, key: str) -> Any:
        """
        Page-level field access — item access (`res["width"]`, the dict-like result path) first,
        then attribute access, so both a serialized dict and a native result object are handled.

        Args:
            res (Any): The page result envelope.
            key (str): Field name to read.

        Returns:
            Any: The value, or None if present on neither shape.
        """
        try:
            value = res[key]
            if value is not None:
                return value
        except (KeyError, TypeError, IndexError):
            pass
        return getattr(res, key, None)

    @staticmethod
    def _get(obj: Any, *names: str) -> Any:
        """
        Block field access over a list of candidate names — attribute then dict key for each — so
        both PaddleOCR-VL's raw names (`block_label`/`block_content`/`block_bbox`) and the
        PP-Structure-style short names (`label`/`content`/`bbox`) resolve.

        Args:
            obj (Any): A block object or dict.
            *names (str): Candidate field names in priority order.

        Returns:
            Any: The first value found, or None when none of the names are present.
        """
        for name in names:
            if hasattr(obj, name):
                return getattr(obj, name)
            if isinstance(obj, dict) and name in obj:
                return obj[name]
        return None


__all__ = ["PaddleOcrVlResponseNormalizer"]

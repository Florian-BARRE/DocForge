# ====== Code Summary ======
# Normalizes MinerU's `content_list.json` (a FLAT, reading-ordered list of blocks) into the SAME clean
# per-page block contract the paddle_server sidecar emits (see paddle_server
# backend/routers/layout_parsing/models.py, mirrored here in ../../backend/routers/parse/models.py).
# Producing an identical wire shape is deliberate: the DocForge IR mapper for `mineru` reuses the
# pp_structure mapper's helpers, so a shared contract means a shared mapper — one place to maintain.
#
# What this module owns (all PURE, no MinerU import — unit-testable from a canned content_list.json):
#   * GROUPING: content_list is one flat list for the whole PDF; blocks carry `page_idx` (0-based).
#     Group by page_idx, preserve list order within a page → reading_order = position in that group.
#   * BBOX: content_list bboxes are `[x0, y0, x1, y1]` normalized to 0–1000 (top-left origin). The VLM
#     model.json path can instead emit 0–1. Detect defensively (a doc whose max coord is ≤ 1 is 0–1 →
#     rescale ×1000) and emit every page with image_width/height = 1000 so the downstream mapper's
#     "divide bbox by page dims" step yields [0, 1] unchanged, whichever space MinerU used.
#   * TYPE → LABEL: MinerU `type` + `text_level` map to the pp_structure-style labels the shared mapper
#     already understands (title/paragraph_title/subsection preserve H1/H2/H3 from text_level;
#     table→table+html; equation→formula+latex; image/chart→figure; list→list+joined items).
#   * CAPTIONS: MinerU attaches `image_caption` / `table_caption` (lists of strings) to their block;
#     they are emitted as a separate `caption` block (same bbox) right after so the text is not lost.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

logger = loggerplusplus.bind(identifier="MineruNormalizer")

# The normalized bbox basis every page is emitted against. content_list is 0–1000 already (0–1 for the
# VLM model.json path is rescaled up to this); the downstream mapper divides by image_width/height =
# BASIS to recover [0, 1], so the basis choice is invisible past this sidecar.
_BBOX_BASIS = 1000
# A doc whose largest bbox coordinate is at/below this is treated as 0–1 normalized (the VLM model.json
# space) and rescaled ×1000; above it, coordinates are assumed to already be in the 0–1000 space.
_UNIT_SPACE_MAX = 1.5


class MineruContentListNormalizer:
    """
    Converts a MinerU `content_list.json` list into the sidecar's per-page HTTP contract.

    Static-only helper (mirrors the sidecar's other static helpers) — never instantiated. Emits the
    SAME `{page_index, image_width, image_height, blocks:[{label, bbox, reading_order,
    text|html|latex}]}` page shape as the paddle_server normalizers so all three sidecars share one
    DocForge IR mapper.
    """

    logger = logger

    def __new__(cls, *args: Any, **kwargs: Any) -> "MineruContentListNormalizer":
        raise TypeError(f"{cls.__name__} is static-only and must not be instantiated.")

    # ── Public API ─────────────────────────────────────────────────────────────────

    @classmethod
    def to_pages(cls, content_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Normalize a whole MinerU content_list into the sidecar's ordered list of page contracts.

        Args:
            content_list (list[dict[str, Any]]): MinerU's flat, reading-ordered block list. Each block
                carries at least `type` and `page_idx`; type-specific content fields as documented.

        Returns:
            list[dict[str, Any]]: One page dict per distinct page_idx, in ascending page order, each
                `{page_index, image_width, image_height, blocks}` (blocks in reading order).
        """
        # 1. Decide the bbox space ONCE for the whole doc (so pages stay consistent), then bucket the
        #    blocks by their 0-based page_idx, preserving MinerU's authoritative list order.
        scale = cls.__bbox_scale(content_list)
        buckets: dict[int, list[dict[str, Any]]] = {}
        for raw in content_list:
            if not isinstance(raw, dict):
                continue
            page_index = cls.__int(raw.get("page_idx"), default=0)
            buckets.setdefault(page_index, []).append(raw)

        # 2. Emit one page per bucket in ascending page order; a block may expand to itself + a caption
        #    block, so reading_order is a per-page running counter, not the source index.
        pages: list[dict[str, Any]] = []
        for page_index in sorted(buckets):
            blocks: list[dict[str, Any]] = []
            for raw in buckets[page_index]:
                for block in cls.__to_blocks(raw, scale):
                    block["reading_order"] = len(blocks)
                    blocks.append(block)
            pages.append(
                {
                    "page_index": page_index,
                    "image_width": _BBOX_BASIS,
                    "image_height": _BBOX_BASIS,
                    "blocks": blocks,
                }
            )
        return pages

    # ── Block mapping ──────────────────────────────────────────────────────────────

    @classmethod
    def __to_blocks(cls, raw: dict[str, Any], scale: float) -> list[dict[str, Any]]:
        """
        Map one MinerU block into one or more contract blocks (the block itself + an optional caption).

        Args:
            raw (dict[str, Any]): One MinerU content_list entry.
            scale (float): Multiplier applied to bbox coordinates (1.0 for a 0–1000 doc, 1000 for 0–1).

        Returns:
            list[dict[str, Any]]: The contract block(s) for this entry (empty if unmappable).
        """
        block_type = str(raw.get("type", "")).strip().lower()
        bbox = cls.__bbox(raw.get("bbox"), scale)

        # 1. Route on the MinerU type to the pp_structure-style label + the one content slot it fills.
        if block_type == "table":
            out = [cls.__block("table", bbox, html=str(raw.get("table_body") or ""))]
            out += cls.__caption_blocks(raw.get("table_caption"), bbox)
            return out
        if block_type == "equation":
            latex = raw.get("text") if raw.get("text_format") == "latex" else raw.get("text")
            return [cls.__block("formula", bbox, latex=str(latex or ""))]
        if block_type in ("image", "chart"):
            out = [cls.__block(block_type, bbox, text="")]
            out += cls.__caption_blocks(raw.get("image_caption"), bbox)
            return out
        if block_type == "list":
            items = raw.get("list_items")
            joined = "\n".join(str(item) for item in items) if isinstance(items, list) else ""
            return [cls.__block("list", bbox, text=joined or str(raw.get("text") or ""))]

        # 2. text / title (and any unknown type) — a text_level ≥ 1 makes it a heading of that level;
        #    a `title` type with no level defaults to a top-level heading; everything else is a
        #    paragraph. Unknown types fall through here as plain text so their content is never dropped.
        label = cls.__text_label(block_type, raw.get("text_level"))
        return [cls.__block(label, bbox, text=str(raw.get("text") or ""))]

    @staticmethod
    def __text_label(block_type: str, text_level: Any) -> str:
        """Resolve a text/title block to a heading label (preserving H1/H2/H3) or a paragraph label."""
        level = text_level if isinstance(text_level, int) else 0
        if block_type == "title" and level <= 0:
            level = 1  # a `title` type with no explicit level is a top-level heading
        if level >= 3:
            return "subsection"  # flattened to level 3 (accepted, as pp_structure/granite)
        if level == 2:
            return "paragraph_title"
        if level == 1:
            return "title"
        return "text"

    @classmethod
    def __caption_blocks(cls, caption: Any, bbox: list[int]) -> list[dict[str, Any]]:
        """Build a `caption` block from a MinerU caption (a list of strings), or [] when absent."""
        if not isinstance(caption, list):
            return []
        text = " ".join(str(part) for part in caption if str(part).strip()).strip()
        if not text:
            return []
        # Share the parent's bbox — content_list gives captions no bbox of their own, and this keeps
        # the caption on the right page for provenance/crop purposes.
        return [cls.__block("caption", list(bbox), text=text)]

    @staticmethod
    def __block(
        label: str,
        bbox: list[int],
        *,
        text: str | None = None,
        html: str | None = None,
        latex: str | None = None,
    ) -> dict[str, Any]:
        """Assemble one contract block dict with exactly the content slot its label needs."""
        block: dict[str, Any] = {"label": label, "bbox": bbox, "reading_order": 0}
        if html is not None:
            block["html"] = html
        elif latex is not None:
            block["latex"] = latex
        else:
            block["text"] = text or ""
        return block

    # ── bbox helpers ───────────────────────────────────────────────────────────────

    @classmethod
    def __bbox_scale(cls, content_list: list[dict[str, Any]]) -> float:
        """
        Decide whether the doc's bboxes are 0–1 (VLM model.json) or 0–1000, returning the multiplier.

        Args:
            content_list (list[dict[str, Any]]): The full block list to sample coordinates from.

        Returns:
            float: 1000.0 when the largest coordinate is ≤ _UNIT_SPACE_MAX (a 0–1 doc), else 1.0.
        """
        max_coord = 0.0
        for raw in content_list:
            if not isinstance(raw, dict):
                continue
            bbox = raw.get("bbox")
            if isinstance(bbox, (list, tuple)):
                for value in bbox:
                    try:
                        max_coord = max(max_coord, abs(float(value)))
                    except (TypeError, ValueError):
                        continue
        if 0.0 < max_coord <= _UNIT_SPACE_MAX:
            return float(_BBOX_BASIS)
        return 1.0

    @classmethod
    def __bbox(cls, bbox: Any, scale: float) -> list[int]:
        """
        Scale a MinerU bbox into the 0–_BBOX_BASIS integer space, degrading to a full-page box.

        Args:
            bbox (Any): The block's `bbox` (expected [x0, y0, x1, y1]).
            scale (float): The doc-wide multiplier from __bbox_scale.

        Returns:
            list[int]: `[x0, y0, x1, y1]` ints in [0, _BBOX_BASIS]; the full page when malformed.
        """
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return [0, 0, _BBOX_BASIS, _BBOX_BASIS]
        try:
            scaled = [int(round(float(value) * scale)) for value in bbox]
        except (TypeError, ValueError):
            return [0, 0, _BBOX_BASIS, _BBOX_BASIS]
        return [max(0, min(_BBOX_BASIS, value)) for value in scaled]

    @staticmethod
    def __int(value: Any, default: int) -> int:
        """Coerce a value to int, falling back to `default` on anything non-numeric."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default


__all__ = ["MineruContentListNormalizer"]

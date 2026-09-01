# ====== Code Summary ======
# Unit tests for PpStructureResponseNormalizer — the sidecar's ONLY paddle-free piece of logic
# (normalizer.py imports nothing but `typing` + `loggerplusplus`, no paddleocr/paddlex/paddlepaddle
# anywhere on the import path). This is the sole coverage that can prove the normalizer "would work"
# on this AVX-less CPU, where PaddlePaddle 3.x itself SIGILLs (exit 132) — see PADDLE-SIDECAR memory.
# Canned PaddleX `res` dicts stand in for real PPStructureV3.predict() output; both documented
# per-block shapes (native LayoutBlock object, attribute access — the pinned 3.7.0 path — and a
# flat dict, the defensive fallback path) are exercised, plus the legacy nested-dict shape to prove
# a version-drifted block degrades instead of crashing.

# ====== Standard Library Imports ======
from types import SimpleNamespace

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from libs.ppstructure.normalizer import PpStructureResponseNormalizer


def _object_block(
    label: str, content: str | None, bbox: list[float], order_index: int | None = None
) -> SimpleNamespace:
    """Build a native-object-shaped block — the pinned paddleocr==3.7.0 `LayoutBlock` path."""
    return SimpleNamespace(label=label, content=content, bbox=bbox, order_index=order_index)


# ── Test: simple page — title + text + table + image ────────────────────────────


def test_simple_page_with_title_text_table_and_image() -> None:
    """
    A page mixing doc_title/text/table/image blocks is normalized into the sidecar contract:
    page-level dims passed through, blocks in reading order, content slotted by label.
    """
    res = {
        "width": 850,
        "height": 1100,
        "page_index": 2,
        "parsing_res_list": [
            _object_block("doc_title", "Report Title", [10, 10, 300, 40], order_index=0),
            _object_block("text", "Body paragraph.", [10, 50, 300, 120], order_index=1),
            _object_block(
                "table", "<table><tr><td>1</td></tr></table>", [10, 130, 300, 300], order_index=2
            ),
            # Plain image block with no in-region text — content is None, not "".
            _object_block("image", None, [320, 10, 600, 300], order_index=3),
        ],
    }

    page = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)

    assert page["page_index"] == 2
    assert page["image_width"] == 850
    assert page["image_height"] == 1100
    assert len(page["blocks"]) == 4

    title, text, table, image = page["blocks"]
    assert title == {
        "label": "doc_title",
        "bbox": [10, 10, 300, 40],
        "reading_order": 0,
        "text": "Report Title",
    }
    assert text["label"] == "text"
    assert text["text"] == "Body paragraph."
    assert table["label"] == "table"
    assert table["html"] == "<table><tr><td>1</td></tr></table>"
    assert "text" not in table
    assert "latex" not in table
    # No in-region text on a plain image block -> empty string, not omitted/None.
    assert image["label"] == "image"
    assert image["text"] == ""


# ── Test: table pred_html / formula rec_formula content slotting ────────────────


def test_table_content_is_slotted_as_html() -> None:
    """A `table` block's already-joined `content` (PaddleX's pred_html) lands in `html`, not `text`."""
    res = {
        "width": 100,
        "height": 100,
        "parsing_res_list": [
            _object_block("table", "<table><tr><td>x</td></tr></table>", [0, 0, 10, 10], 0),
        ],
    }

    block = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"][0]

    assert block["html"] == "<table><tr><td>x</td></tr></table>"
    assert "text" not in block
    assert "latex" not in block


def test_formula_content_is_slotted_as_latex() -> None:
    """A `formula` block's already-joined `content` (PaddleX's rec_formula) lands in `latex`."""
    res = {
        "width": 100,
        "height": 100,
        "parsing_res_list": [
            _object_block("formula", "E = mc^2", [0, 0, 10, 10], 0),
        ],
    }

    block = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"][0]

    assert block["latex"] == "E = mc^2"
    assert "text" not in block
    assert "html" not in block


def test_table_content_none_slots_as_empty_html() -> None:
    """A table block with no recognized content still gets `html`, defaulted to "" (never None)."""
    res = {
        "width": 100,
        "height": 100,
        "parsing_res_list": [_object_block("table", None, [0, 0, 10, 10], 0)],
    }

    block = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"][0]

    assert block["html"] == ""


# ── Test: reading order ──────────────────────────────────────────────────────────


def test_blocks_are_reordered_by_order_index_not_input_position() -> None:
    """Blocks arrive out of order; the output is sorted by `order_index`, and `reading_order`
    is a freshly assigned 0-based position — NOT a copy of the original `order_index` value."""
    res = {
        "width": 100,
        "height": 100,
        "parsing_res_list": [
            _object_block("text", "third", [0, 0, 1, 1], order_index=10),
            _object_block("text", "first", [0, 0, 1, 1], order_index=1),
            _object_block("text", "second", [0, 0, 1, 1], order_index=5),
        ],
    }

    blocks = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"]

    assert [b["text"] for b in blocks] == ["first", "second", "third"]
    assert [b["reading_order"] for b in blocks] == [0, 1, 2]


def test_sort_key_falls_back_to_index_when_order_index_missing() -> None:
    """When `order_index` is None, the block falls back to `index` for its sort position."""
    res = {
        "width": 100,
        "height": 100,
        "parsing_res_list": [
            SimpleNamespace(
                label="text", content="second", bbox=[0, 0, 1, 1], order_index=None, index=2
            ),
            SimpleNamespace(
                label="text", content="first", bbox=[0, 0, 1, 1], order_index=None, index=0
            ),
        ],
    }

    blocks = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"]

    assert [b["text"] for b in blocks] == ["first", "second"]


def test_sort_key_defaults_to_zero_when_neither_order_index_nor_index_present() -> None:
    """A block exposing neither `order_index` nor `index` sorts as position 0 (defensive, never
    crashes) rather than raising — proven by mixing it with a definitively-ordered block."""
    res = {
        "width": 100,
        "height": 100,
        "parsing_res_list": [
            _object_block("text", "explicit-first", [0, 0, 1, 1], order_index=5),
            SimpleNamespace(label="text", content="no-order-info", bbox=[0, 0, 1, 1]),
        ],
    }

    blocks = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"]

    # The block with no order info sorts as key 0 -> comes first, ahead of order_index=5.
    assert [b["text"] for b in blocks] == ["no-order-info", "explicit-first"]


# ── Test: the two documented per-block schema variants ───────────────────────────


def test_native_layoutblock_object_variant() -> None:
    """Primary path (pinned paddleocr==3.7.0): a `LayoutBlock`-like object, attribute access."""
    block = SimpleNamespace(
        label="paragraph_title", content="Section 1", bbox=[1, 2, 3, 4], order_index=0
    )
    res = {"width": 100, "height": 100, "parsing_res_list": [block]}

    out = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"][0]

    assert out == {
        "label": "paragraph_title",
        "bbox": [1, 2, 3, 4],
        "reading_order": 0,
        "text": "Section 1",
    }


def test_flat_dict_block_variant() -> None:
    """Defensive fallback path: a flat dict block (`{label, bbox, content, order_index}`) — the
    `_get` dict branch — is handled identically to the native-object path."""
    block = {"label": "text", "content": "Flat-dict body", "bbox": [5, 6, 7, 8], "order_index": 0}
    res = {"width": 100, "height": 100, "parsing_res_list": [block]}

    out = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"][0]

    assert out == {
        "label": "text",
        "bbox": [5, 6, 7, 8],
        "reading_order": 0,
        "text": "Flat-dict body",
    }


def test_legacy_nested_dict_shape_degrades_without_crashing() -> None:
    """PaddleOCR release/3.0's nested `parsing_res_list` shape (`{layout_bbox, "{label}": content,
    layout}`, label as a dynamic dict key — see revision.py) is NOT understood by `_get` (it only
    looks up flat `label`/`bbox`/`content`/`order_index` keys) — it must degrade to a defensive
    text-only block with a zeroed bbox, not raise."""
    legacy_block = {
        "layout_bbox": [1, 2, 3, 4],
        "text_region": "some content",
        "layout": "vertical",
    }
    res = {"width": 100, "height": 100, "parsing_res_list": [legacy_block]}

    out = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"][0]

    assert out == {"label": "", "bbox": [0, 0, 0, 0], "reading_order": 0, "text": ""}


# ── Test: page-image pixel dims passthrough ───────────────────────────────────────


def test_image_dims_are_cast_to_int() -> None:
    """`width`/`height` are cast to int even if PaddleX hands back float pixel dims."""
    res = {"width": 812.0, "height": 1200.0, "parsing_res_list": []}

    page = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)

    assert page["image_width"] == 812
    assert page["image_height"] == 1200
    assert isinstance(page["image_width"], int)
    assert isinstance(page["image_height"], int)


def test_image_dims_default_to_zero_when_missing() -> None:
    """Missing `width`/`height` default to 0 (a caller-side 0-divisor guard, not this module's job)."""
    res: dict[str, object] = {"parsing_res_list": []}

    page = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)

    assert page["image_width"] == 0
    assert page["image_height"] == 0


def test_bbox_coordinates_are_truncated_to_int() -> None:
    """Sub-pixel float bbox coordinates are truncated (via `int()`), not rounded."""
    res = {
        "width": 100,
        "height": 100,
        "parsing_res_list": [_object_block("text", "x", [10.9, 20.1, 30.5, 40.99], 0)],
    }

    block = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"][0]

    assert block["bbox"] == [10, 20, 30, 40]


def test_missing_bbox_defaults_to_zero_bbox() -> None:
    """A block with no `bbox` at all (defensive, should never happen on a healthy result) defaults
    to `[0, 0, 0, 0]` instead of raising."""
    block = SimpleNamespace(label="text", content="x", bbox=None, order_index=0)
    res = {"width": 100, "height": 100, "parsing_res_list": [block]}

    out = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"][0]

    assert out["bbox"] == [0, 0, 0, 0]


# ── Test: page_index fallback ─────────────────────────────────────────────────────


def test_page_index_uses_fallback_when_absent() -> None:
    """A result with no `page_index` (e.g. a single-image input) falls back to the caller-supplied
    0-based predict() list position."""
    res = {"width": 100, "height": 100, "parsing_res_list": []}

    page = PpStructureResponseNormalizer.to_page(res, fallback_page_index=3)

    assert page["page_index"] == 3


def test_page_index_present_overrides_fallback() -> None:
    """An explicit `page_index` on the result always wins over the fallback position."""
    res = {"width": 100, "height": 100, "page_index": 7, "parsing_res_list": []}

    page = PpStructureResponseNormalizer.to_page(res, fallback_page_index=3)

    assert page["page_index"] == 7


# ── Test: degenerate empty page ───────────────────────────────────────────────────


def test_empty_parsing_res_list_yields_no_blocks() -> None:
    """A page with an empty `parsing_res_list` normalizes to an empty `blocks` list, not an error."""
    res = {"width": 100, "height": 100, "parsing_res_list": []}

    page = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)

    assert page["blocks"] == []


def test_none_parsing_res_list_yields_no_blocks() -> None:
    """`parsing_res_list` itself being None (defensive) also normalizes to an empty block list."""
    res = {"width": 100, "height": 100, "parsing_res_list": None}

    page = PpStructureResponseNormalizer.to_page(res, fallback_page_index=0)

    assert page["blocks"] == []


# ── Test: static-only class ───────────────────────────────────────────────────────


def test_instantiation_is_blocked() -> None:
    """PpStructureResponseNormalizer is a static-only class and must reject direct instantiation."""
    with pytest.raises(TypeError):
        PpStructureResponseNormalizer()

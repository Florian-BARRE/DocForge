# ====== Code Summary ======
# Unit tests for PaddleOcrVlResponseNormalizer — the VL sidecar's paddle-free normalizer (imports
# nothing but `typing` + `loggerplusplus`, no paddleocr/paddlex/paddlepaddle on the import path), so
# this coverage runs on the AVX-less CI CPU where PaddlePaddle itself SIGILLs (exit 132). The primary
# assertions run over a REAL captured PaddleOCR-VL 1.6 sample envelope (fixtures/paddleocr_vl_sample
# .json — attention.pdf p8 with a rowspan table + multifig.pdf p0 with images); synthetic dict/object
# blocks cover the raw-name / short-name and object/dict access variants and the reading-order rule.

# ====== Standard Library Imports ======
import json
import pathlib
from types import SimpleNamespace

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from libs.paddleocr_vl.normalizer import PaddleOcrVlResponseNormalizer

# The real captured two-page envelope (top-level page keys); each value is a raw page result.
_SAMPLE = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "paddleocr_vl_sample.json").read_text()
)
_PAGE_A = _SAMPLE["page_A_attention_p8_with_table"]  # table page, page_index null
_PAGE_B = _SAMPLE["page_B_multifig_p0_with_image"]  # image page, page_index 0


def _raw_block(
    label: str, content: str | None, bbox: list[float], block_order: int | None = None
) -> dict:
    """Build a raw PaddleOCR-VL block dict (the captured `block_*` field names)."""
    return {
        "block_label": label,
        "block_content": content,
        "block_bbox": bbox,
        "block_order": block_order,
    }


# ── Test: the real captured table page ───────────────────────────────────────────


def test_real_sample_table_page_normalizes_to_the_contract() -> None:
    """The captured table page (page_index null) normalizes: dims passed through, list-order reading
    order, table→html / figure_title→text / number→text / image→text-empty."""
    page = PaddleOcrVlResponseNormalizer.to_page(_PAGE_A, fallback_page_index=0)

    assert page["image_width"] == 1224
    assert page["image_height"] == 1584
    assert page["page_index"] == 0  # page_index was null → fallback used
    assert len(page["blocks"]) == 10
    # reading_order is the block's list position (parsing_res_list is already visually ordered).
    assert [b["reading_order"] for b in page["blocks"]] == list(range(10))

    caption, table = page["blocks"][0], page["blocks"][1]
    assert caption["label"] == "figure_title"
    assert caption["text"].startswith("Table 3:")
    assert table["label"] == "table"
    assert table["html"].startswith("<table>")
    assert "text" not in table and "latex" not in table
    # The page-number block keeps its text (mapped, not dropped, at the sidecar level).
    number = page["blocks"][9]
    assert number["label"] == "number"
    assert number["text"] == "9"


def test_real_sample_image_page_slots_image_as_empty_text() -> None:
    """On the captured image page, an `image` block (empty block_content) becomes text=""."""
    page = PaddleOcrVlResponseNormalizer.to_page(_PAGE_B, fallback_page_index=0)

    assert page["page_index"] == 0
    images = [b for b in page["blocks"] if b["label"] == "image"]
    assert len(images) == 2
    for image in images:
        assert image["text"] == ""
        assert "html" not in image and "latex" not in image
    # Reading order stays list order: doc_title first, the Section-3 text last.
    assert page["blocks"][0]["label"] == "doc_title"
    assert [b["reading_order"] for b in page["blocks"]] == list(range(11))


# ── Test: content slotting by label ──────────────────────────────────────────────


def test_table_content_is_slotted_as_html() -> None:
    """A `table` block's block_content (the HTML string) lands in `html`, not `text`."""
    res = {
        "width": 100,
        "height": 100,
        "parsing_res_list": [
            _raw_block("table", "<table><tr><td>x</td></tr></table>", [0, 0, 10, 10], 0)
        ],
    }
    block = PaddleOcrVlResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"][0]
    assert block["html"] == "<table><tr><td>x</td></tr></table>"
    assert "text" not in block and "latex" not in block


def test_formula_content_is_slotted_as_latex() -> None:
    """A `formula` block's block_content (raw LaTeX) lands in `latex`."""
    res = {
        "width": 100,
        "height": 100,
        "parsing_res_list": [_raw_block("formula", "E = mc^2", [0, 0, 10, 10], 0)],
    }
    block = PaddleOcrVlResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"][0]
    assert block["latex"] == "E = mc^2"
    assert "text" not in block and "html" not in block


def test_image_content_none_slots_as_empty_text() -> None:
    """An image block with None block_content still gets `text`, defaulted to "" (never None)."""
    res = {
        "width": 100,
        "height": 100,
        "parsing_res_list": [_raw_block("image", None, [0, 0, 10, 10], None)],
    }
    block = PaddleOcrVlResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"][0]
    assert block["text"] == ""


# ── Test: reading order is list order (block_order NOT re-sorted) ─────────────────


def test_reading_order_follows_list_position_not_block_order() -> None:
    """parsing_res_list is already reading-ordered; the normalizer keeps that list order and does NOT
    re-sort on block_order (which is None on tables/figures/captions and would interleave them)."""
    res = {
        "width": 100,
        "height": 100,
        "parsing_res_list": [
            _raw_block("figure_title", "cap", [0, 0, 1, 1], None),  # None order, but comes first
            _raw_block("table", "<table></table>", [0, 0, 1, 1], None),
            _raw_block("text", "first-text", [0, 0, 1, 1], 1),
            _raw_block("text", "second-text", [0, 0, 1, 1], 2),
        ],
    }
    blocks = PaddleOcrVlResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"]
    assert [b["label"] for b in blocks] == ["figure_title", "table", "text", "text"]
    assert [b["reading_order"] for b in blocks] == [0, 1, 2, 3]


# ── Test: object-shaped blocks + short field names ───────────────────────────────


def test_native_object_block_with_short_names_is_handled() -> None:
    """A native result object exposing `.label`/`.content`/`.bbox` (short names) resolves too."""
    block = SimpleNamespace(label="paragraph_title", content="Section 1", bbox=[1, 2, 3, 4])
    res = {"width": 100, "height": 100, "parsing_res_list": [block]}
    out = PaddleOcrVlResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"][0]
    assert out == {
        "label": "paragraph_title",
        "bbox": [1, 2, 3, 4],
        "reading_order": 0,
        "text": "Section 1",
    }


def test_object_shaped_page_envelope_is_handled() -> None:
    """A page envelope exposing attributes (not item access) resolves via the attribute fallback."""
    block = {"block_label": "text", "block_content": "body", "block_bbox": [0, 0, 1, 1]}
    res = SimpleNamespace(width=800, height=600, page_index=4, parsing_res_list=[block])
    page = PaddleOcrVlResponseNormalizer.to_page(res, fallback_page_index=0)
    assert page["image_width"] == 800
    assert page["image_height"] == 600
    assert page["page_index"] == 4
    assert page["blocks"][0]["text"] == "body"


# ── Test: bbox + dims casting / defaults ─────────────────────────────────────────


def test_bbox_coordinates_are_truncated_to_int() -> None:
    """Sub-pixel float bbox coordinates are truncated (via int()), not rounded."""
    res = {
        "width": 100,
        "height": 100,
        "parsing_res_list": [_raw_block("text", "x", [10.9, 20.1, 30.5, 40.99], 0)],
    }
    block = PaddleOcrVlResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"][0]
    assert block["bbox"] == [10, 20, 30, 40]


def test_missing_bbox_defaults_to_zero_bbox() -> None:
    """A block with no bbox defaults to [0, 0, 0, 0] instead of raising."""
    res = {
        "width": 100,
        "height": 100,
        "parsing_res_list": [_raw_block("text", "x", None, 0)],  # type: ignore[arg-type]
    }
    out = PaddleOcrVlResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"][0]
    assert out["bbox"] == [0, 0, 0, 0]


def test_image_dims_default_to_zero_when_missing() -> None:
    """Missing width/height default to 0 (a caller-side 0-divisor guard, not this module's job)."""
    res: dict[str, object] = {"parsing_res_list": []}
    page = PaddleOcrVlResponseNormalizer.to_page(res, fallback_page_index=0)
    assert page["image_width"] == 0
    assert page["image_height"] == 0


# ── Test: page_index fallback ─────────────────────────────────────────────────────


def test_page_index_uses_fallback_when_absent() -> None:
    """A result with no page_index falls back to the caller-supplied predict() list position."""
    res = {"width": 100, "height": 100, "parsing_res_list": []}
    page = PaddleOcrVlResponseNormalizer.to_page(res, fallback_page_index=3)
    assert page["page_index"] == 3


def test_page_index_present_overrides_fallback() -> None:
    """An explicit page_index on the result always wins over the fallback position."""
    res = {"width": 100, "height": 100, "page_index": 7, "parsing_res_list": []}
    page = PaddleOcrVlResponseNormalizer.to_page(res, fallback_page_index=3)
    assert page["page_index"] == 7


# ── Test: degenerate empty page ───────────────────────────────────────────────────


def test_empty_parsing_res_list_yields_no_blocks() -> None:
    """A page with an empty parsing_res_list normalizes to an empty blocks list, not an error."""
    res = {"width": 100, "height": 100, "parsing_res_list": []}
    assert PaddleOcrVlResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"] == []


def test_none_parsing_res_list_yields_no_blocks() -> None:
    """parsing_res_list itself being None (defensive) also normalizes to an empty block list."""
    res = {"width": 100, "height": 100, "parsing_res_list": None}
    assert PaddleOcrVlResponseNormalizer.to_page(res, fallback_page_index=0)["blocks"] == []


# ── Test: static-only class ───────────────────────────────────────────────────────


def test_instantiation_is_blocked() -> None:
    """PaddleOcrVlResponseNormalizer is a static-only class and must reject instantiation."""
    with pytest.raises(TypeError):
        PaddleOcrVlResponseNormalizer()

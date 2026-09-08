"""Unit tests for the MinerU content_list -> sidecar-contract normalizer.

Everything is offline: the normalizer is pure (no MinerU/torch/CUDA import) and runs over a synthetic
content_list.json built from MinerU's documented schema (type / bbox 0-1000 / page_idx / text_level /
table_body HTML / equation latex / image_caption / list_items). This is the fully-tested half of the
brick; the ONE untested seam is libs/mineru/engine.py's real MinerU call (GPU-only — see its docstring).
"""

import json
import pathlib

from libs.mineru.normalizer import MineruContentListNormalizer

# ==================== the synthetic content_list fixture ====================

_CONTENT_LIST = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "content_list.json").read_text()
)


# ==================== grouping + paging ====================


def test_groups_blocks_by_page_and_orders_pages() -> None:
    """The flat content_list splits into two pages (page_idx 0 and 1) in ascending order."""
    pages = MineruContentListNormalizer.to_pages(_CONTENT_LIST)
    assert [p["page_index"] for p in pages] == [0, 1]
    # Every page is emitted against the 0-1000 normalization basis.
    for page in pages:
        assert page["image_width"] == 1000
        assert page["image_height"] == 1000


def test_reading_order_is_per_page_list_position() -> None:
    """reading_order is a per-page running counter following MinerU's list order (captions inserted)."""
    pages = MineruContentListNormalizer.to_pages(_CONTENT_LIST)
    page0, page1 = pages
    assert [b["reading_order"] for b in page0["blocks"]] == list(range(len(page0["blocks"])))
    assert [b["reading_order"] for b in page1["blocks"]] == list(range(len(page1["blocks"])))


# ==================== type -> label + content slot ====================


def test_heading_levels_preserved_from_text_level() -> None:
    """text_level 1 -> title (H1), 2 -> paragraph_title (H2), >=3 -> subsection (H3, flattened)."""
    pages = MineruContentListNormalizer.to_pages(_CONTENT_LIST)
    labels_p0 = [b["label"] for b in pages[0]["blocks"]]
    # First page opens with the H1 title, then a body paragraph, then the H2 section header.
    assert labels_p0[0] == "title"
    assert labels_p0[1] == "text"
    assert labels_p0[2] == "paragraph_title"
    # The text_level=4 heading on page 1 flattens to subsection (level 3).
    labels_p1 = [b["label"] for b in pages[1]["blocks"]]
    assert "subsection" in labels_p1


def test_table_maps_to_html_slot_with_caption_block() -> None:
    """A table block carries its HTML in the `html` slot; its caption becomes a separate caption block."""
    pages = MineruContentListNormalizer.to_pages(_CONTENT_LIST)
    blocks = pages[0]["blocks"]
    table = next(b for b in blocks if b["label"] == "table")
    assert table["html"].startswith("<table>")
    assert "text" not in table and "latex" not in table
    # A caption block immediately follows the table, carrying the table_caption text.
    caption = next(b for b in blocks if b["label"] == "caption")
    assert caption["text"] == "Table 1: Maximum path lengths."


def test_equation_maps_to_latex_slot() -> None:
    """An equation block carries its LaTeX in the `latex` slot, mapped to the `formula` label."""
    pages = MineruContentListNormalizer.to_pages(_CONTENT_LIST)
    formula = next(b for b in pages[1]["blocks"] if b["label"] == "formula")
    assert formula["latex"].startswith("\\mathrm{Attention}")
    assert "text" not in formula and "html" not in formula


def test_image_maps_to_empty_figure_with_caption_block() -> None:
    """An image block is an empty `image` placeholder (empty text) + a following caption block."""
    pages = MineruContentListNormalizer.to_pages(_CONTENT_LIST)
    blocks = pages[1]["blocks"]
    image = next(b for b in blocks if b["label"] == "image")
    assert image["text"] == ""
    caption = next(b for b in blocks if b["label"] == "caption")
    assert caption["text"] == "Figure 1: The Transformer architecture."


def test_list_items_joined_into_text() -> None:
    """A list block joins its list_items into the `text` slot under the `list` label."""
    pages = MineruContentListNormalizer.to_pages(_CONTENT_LIST)
    list_block = next(b for b in pages[1]["blocks"] if b["label"] == "list")
    assert list_block["text"] == "First point.\nSecond point.\nThird point."


# ==================== bbox handling ====================


def test_bbox_0_1000_kept_as_pixels_in_basis() -> None:
    """A 0-1000 bbox is passed through as ints in the 0-1000 basis (the downstream mapper divides)."""
    pages = MineruContentListNormalizer.to_pages(_CONTENT_LIST)
    title = pages[0]["blocks"][0]
    assert title["bbox"] == [100, 80, 900, 140]


def test_bbox_0_1_space_is_rescaled_to_basis() -> None:
    """A document whose bboxes are 0-1 (the VLM model.json space) is rescaled x1000 to the basis."""
    unit_doc = [
        {"type": "text", "text": "a", "page_idx": 0, "bbox": [0.1, 0.08, 0.9, 0.14]},
        {"type": "text", "text": "b", "page_idx": 0, "bbox": [0.0, 0.5, 1.0, 0.6]},
    ]
    pages = MineruContentListNormalizer.to_pages(unit_doc)
    assert pages[0]["blocks"][0]["bbox"] == [100, 80, 900, 140]
    assert pages[0]["blocks"][1]["bbox"] == [0, 500, 1000, 600]


def test_malformed_bbox_degrades_to_full_page() -> None:
    """A malformed bbox degrades to the full-page box rather than dropping the block."""
    doc = [{"type": "text", "text": "x", "page_idx": 0, "bbox": [1, 2, 3]}]
    pages = MineruContentListNormalizer.to_pages(doc)
    assert pages[0]["blocks"][0]["bbox"] == [0, 0, 1000, 1000]


def test_empty_content_list_yields_no_pages() -> None:
    """An empty content_list produces no pages (a degenerate but valid parse)."""
    assert MineruContentListNormalizer.to_pages([]) == []

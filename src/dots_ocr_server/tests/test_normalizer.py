"""Unit tests for the dots.ocr per-page output -> sidecar-contract normalizer.

Everything is offline: the normalizer is pure (no vllm/torch/CUDA import) and runs over a synthetic
dots.ocr page output (a JSON string listing layout elements, built from the documented schema:
category / bbox pixels / text / reading_order). This is the fully-tested half of the brick; the ONE
untested seam is libs/dots_ocr/engine.py's real render + vLLM call (GPU-only — see its docstring).
"""

import json
import pathlib

from libs.dots_ocr.normalizer import DotsOcrPageNormalizer

# ==================== the synthetic per-page element list ====================

_ELEMENTS = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "dots_ocr_page.json").read_text()
)
_RAW = json.dumps(_ELEMENTS)


def _page(width: int = 1000, height: int = 1400, raw: str | None = None) -> dict:
    """Normalize the fixture page (or a supplied raw output) at the given rendered dims."""
    return DotsOcrPageNormalizer.to_page(
        page_index=0,
        image_width=width,
        image_height=height,
        raw_output=_RAW if raw is None else raw,
    )


# ==================== page shape + reading order ====================


def test_page_carries_the_rendered_pixel_dims() -> None:
    """The page echoes the rendered image dims — the bbox divisor the DocForge mapper uses."""
    page = _page(width=1224, height=1584)
    assert page["page_index"] == 0
    assert page["image_width"] == 1224
    assert page["image_height"] == 1584


def test_reading_order_follows_the_model_reading_order() -> None:
    """Blocks are ordered by the element `reading_order`, re-indexed 0..n per page."""
    page = _page()
    labels = [b["label"] for b in page["blocks"]]
    assert labels == ["Title", "Text", "Section-header", "Table", "Formula", "Picture"]
    assert [b["reading_order"] for b in page["blocks"]] == list(range(6))


def test_reading_order_field_actually_sorts() -> None:
    """A shuffled input is re-sorted by the element `reading_order` field, not by list position."""
    shuffled = json.dumps(
        [
            {"category": "Text", "bbox": [0, 10, 10, 20], "reading_order": 2, "text": "second"},
            {"category": "Title", "bbox": [0, 0, 10, 5], "reading_order": 0, "text": "first"},
            {"category": "Text", "bbox": [0, 30, 10, 40], "reading_order": 1, "text": "middle"},
        ]
    )
    page = _page(raw=shuffled)
    assert [b.get("text") for b in page["blocks"]] == ["first", "middle", "second"]


# ==================== category -> content slot ====================


def test_table_text_goes_into_the_html_slot() -> None:
    """A Table element's text (HTML) lands in the `html` slot, not `text`."""
    page = _page()
    table = next(b for b in page["blocks"] if b["label"] == "Table")
    assert table["html"].startswith("<table>")
    assert "text" not in table and "latex" not in table


def test_formula_text_goes_into_the_latex_slot() -> None:
    """A Formula element's text (LaTeX) lands in the `latex` slot, not `text`."""
    page = _page()
    formula = next(b for b in page["blocks"] if b["label"] == "Formula")
    assert formula["latex"] == "\\mathrm{softmax}(x)"
    assert "text" not in formula and "html" not in formula


def test_picture_has_empty_text_and_no_html_latex() -> None:
    """A Picture element carries no recognized text (the crop is filled downstream by figure_render)."""
    page = _page()
    picture = next(b for b in page["blocks"] if b["label"] == "Picture")
    assert picture["text"] == ""
    assert "html" not in picture and "latex" not in picture


def test_plain_text_categories_go_into_the_text_slot() -> None:
    """Title/Text/Section-header carry their Markdown/plain text in the `text` slot."""
    page = _page()
    title = next(b for b in page["blocks"] if b["label"] == "Title")
    assert title["text"] == "Attention Is All You Need"


# ==================== bbox handling ====================


def test_pixel_bbox_is_passed_through_as_ints() -> None:
    """A pixel bbox is kept verbatim (the DocForge mapper divides by the page dims, not the sidecar)."""
    page = _page()
    title = next(b for b in page["blocks"] if b["label"] == "Title")
    assert title["bbox"] == [100, 80, 900, 140]


def test_malformed_bbox_degrades_to_full_page() -> None:
    """A malformed bbox degrades to the full rendered page box rather than dropping the block."""
    raw = json.dumps([{"category": "Text", "bbox": [1, 2, 3], "reading_order": 0, "text": "x"}])
    page = _page(width=800, height=600, raw=raw)
    assert page["blocks"][0]["bbox"] == [0, 0, 800, 600]


def test_high_bbox_fallback_rate_warns(monkeypatch) -> None:
    """When most elements lack a valid bbox, the normalizer warns (a schema-drift tripwire).

    loggerplusplus wraps loguru, which does not feed pytest's caplog — so the warning is captured by
    swapping the normalizer's bound logger for a recorder.
    """
    warnings: list[str] = []

    class _Recorder:
        def warning(self, message: str) -> None:
            warnings.append(message)

        def __getattr__(self, _name: str):  # debug/info/error are no-ops in this test
            return lambda *args, **kwargs: None

    monkeypatch.setattr(DotsOcrPageNormalizer, "logger", _Recorder())
    raw = json.dumps(
        [
            {"category": "Text", "bbox": None, "reading_order": 0, "text": "a"},
            {"category": "Text", "bbox": "bad", "reading_order": 1, "text": "b"},
            {"category": "Text", "bbox": [0, 0, 10, 10], "reading_order": 2, "text": "c"},
        ]
    )
    page = _page(raw=raw)
    assert len(page["blocks"]) == 3
    assert any("fell back to a full-page bbox" in message for message in warnings)


# ==================== JSON parsing robustness ====================


def test_json_fence_is_stripped() -> None:
    """A ```json fenced model output is unwrapped before decoding (VLMs commonly fence JSON)."""
    fenced = "```json\n" + _RAW + "\n```"
    page = _page(raw=fenced)
    assert len(page["blocks"]) == 6


def test_non_json_output_degrades_to_empty_page() -> None:
    """A non-JSON model output yields an empty page (logged) rather than crashing the parse."""
    page = _page(raw="I could not read this document.")
    assert page["blocks"] == []


def test_non_list_json_degrades_to_empty_page() -> None:
    """A JSON object (not a list of elements) degrades to an empty page."""
    page = _page(raw=json.dumps({"category": "Text"}))
    assert page["blocks"] == []


def test_empty_output_yields_no_blocks() -> None:
    """An empty model output produces an empty block list (a degenerate but valid page)."""
    page = _page(raw="")
    assert page["blocks"] == []

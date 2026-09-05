"""The Docling→IR provenance mapper: a bbox must always normalize to a FINITE bbox inside the [0, 1]
unit square, even when the page size is degenerate (missing/zero/negative dimension) or the bbox
coordinates fall outside the page or are non-finite. This is the Provenance bbox contract the
pp_structure parser already honors; docling now matches it. All fakes are plain objects — no docling
install is needed (the helpers module imports no docling).
"""

import math

from shared_libs.pipelines.ingest.nodes.parse.parser.docling.helpers import DoclingParseHelpers


class _FakeBBox:
    """A stand-in Docling bbox (l/t/r/b + coord origin)."""

    def __init__(
        self, left: float, top: float, right: float, bottom: float, origin: str = "TOPLEFT"
    ):
        self.l = left  # noqa: E741 — mirrors docling's single-letter bbox attribute names
        self.t = top
        self.r = right
        self.b = bottom
        self.coord_origin = origin


class _FakeProv:
    """A stand-in Docling provenance entry (1-indexed page + bbox)."""

    def __init__(self, page_no: int, bbox: _FakeBBox):
        self.page_no = page_no
        self.bbox = bbox


class _FakeSize:
    def __init__(self, width, height):
        self.width = width
        self.height = height


class _FakePage:
    def __init__(self, size):
        self.size = size


class _FakeItem:
    def __init__(self, prov):
        self.prov = prov


class _FakeDoc:
    def __init__(self, pages):
        self.pages = pages


def _assert_finite_unit(bbox) -> None:
    for value in bbox:
        assert math.isfinite(value), bbox
        assert 0.0 <= value <= 1.0, bbox


def test_zero_page_size_degrades_to_a_finite_clamped_bbox() -> None:
    """A zero page dimension must not divide-by-zero nor produce inf/NaN — it degrades to 1.0 and the
    raw coordinates then clamp into [0, 1] (matches the pp_structure full-page degrade)."""
    item = _FakeItem([_FakeProv(1, _FakeBBox(10, 20, 30, 40))])
    doc = _FakeDoc({1: _FakePage(_FakeSize(width=0, height=0))})
    prov = DoclingParseHelpers.extract_provenance(item, doc)
    assert prov is not None
    _assert_finite_unit(prov.bbox)
    assert prov.bbox == (1.0, 1.0, 1.0, 1.0)


def test_out_of_range_coordinates_are_clamped_into_the_unit_square() -> None:
    """Coordinates beyond the page (or negative) clamp to [0, 1] instead of leaking a raw ratio."""
    item = _FakeItem([_FakeProv(1, _FakeBBox(left=-50, top=80, right=1200, bottom=900))])
    doc = _FakeDoc({1: _FakePage(_FakeSize(width=1000, height=800))})
    prov = DoclingParseHelpers.extract_provenance(item, doc)
    assert prov is not None
    _assert_finite_unit(prov.bbox)
    x0, y0, x1, y1 = prov.bbox
    assert x0 == 0.0  # -50/1000 clamped up to 0
    assert x1 == 1.0  # 1200/1000 clamped down to 1
    assert y0 == 0.1  # 80/800 in range, untouched
    assert y1 == 1.0  # 900/800 clamped down to 1


def test_missing_page_object_degrades_without_crashing() -> None:
    """A prov page with no matching page object (size None) still yields a finite in-range bbox."""
    item = _FakeItem([_FakeProv(2, _FakeBBox(5, 5, 15, 15))])
    doc = _FakeDoc({})  # page 2 absent
    prov = DoclingParseHelpers.extract_provenance(item, doc)
    assert prov is not None
    _assert_finite_unit(prov.bbox)


def test_non_finite_coordinates_map_to_finite_values() -> None:
    """A NaN/inf coordinate (a corrupt bbox) collapses to a finite in-range value, never propagates."""
    item = _FakeItem(
        [_FakeProv(1, _FakeBBox(left=float("nan"), top=float("inf"), right=10, bottom=20))]
    )
    doc = _FakeDoc({1: _FakePage(_FakeSize(width=100, height=100))})
    prov = DoclingParseHelpers.extract_provenance(item, doc)
    assert prov is not None
    _assert_finite_unit(prov.bbox)

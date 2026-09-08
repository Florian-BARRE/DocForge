"""Unit tests for the Qwen2-VL smart_resize dim computation (pure, offline).

dots.ocr returns bboxes in the smart-resized frame its vision encoder sees, so the sidecar must resize
each page to exactly these dims and report them as the bbox divisor. The algorithm is pure arithmetic —
fully testable here without a GPU.
"""

import pytest

from libs.dots_ocr.resize import SmartResize

_FACTOR = 28
_MIN_PIXELS = 3136
_MAX_PIXELS = 11289600


@pytest.mark.parametrize(
    "height,width",
    [
        (100, 100),  # tiny — must scale UP to reach min_pixels
        (1584, 1224),  # a typical rendered document page
        (2200, 1700),  # a larger scan
        (20000, 100),  # extreme aspect ratio
        (8000, 8000),  # huge — must scale DOWN under max_pixels
    ],
)
def test_dims_are_multiples_of_factor_and_within_budget(height: int, width: int) -> None:
    """Every output side is a positive multiple of the factor and the area fits the pixel budget."""
    out_h, out_w = SmartResize.dims(
        height, width, factor=_FACTOR, min_pixels=_MIN_PIXELS, max_pixels=_MAX_PIXELS
    )
    # 1. Both sides are positive multiples of the factor (what the vision encoder requires).
    assert out_h > 0 and out_w > 0
    assert out_h % _FACTOR == 0
    assert out_w % _FACTOR == 0
    # 2. The materialized area respects the max budget (down-scale case) and reaches the min.
    assert out_h * out_w <= _MAX_PIXELS
    assert out_h * out_w >= _MIN_PIXELS


def test_already_conformant_dims_are_stable() -> None:
    """A page already at a multiple of the factor inside the budget is returned unchanged."""
    out_h, out_w = SmartResize.dims(
        1120, 784, factor=_FACTOR, min_pixels=_MIN_PIXELS, max_pixels=_MAX_PIXELS
    )
    assert (out_h, out_w) == (1120, 784)


def test_aspect_ratio_is_roughly_preserved_on_downscale() -> None:
    """Down-scaling a wide page keeps width > height (the orientation is not flipped)."""
    out_h, out_w = SmartResize.dims(
        4000, 8000, factor=_FACTOR, min_pixels=_MIN_PIXELS, max_pixels=_MAX_PIXELS
    )
    assert out_w > out_h
    assert out_h * out_w <= _MAX_PIXELS

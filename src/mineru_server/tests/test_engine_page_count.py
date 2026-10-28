"""Unit tests for MineruEngine's page count over a content_list (pure, offline, no GPU)."""

from libs.mineru.engine import MineruEngine


def test_page_count_skips_blocks_without_a_usable_page_idx() -> None:
    """A missing, None or non-numeric page_idx is skipped; the highest valid 0-based index wins."""
    content_list = [
        {"page_idx": 0},
        {"page_idx": None},
        {"type": "text"},
        {"page_idx": "x"},
        {"page_idx": 2},
    ]

    assert MineruEngine._MineruEngine__page_count(content_list) == 3  # type: ignore[attr-defined]


def test_page_count_is_zero_without_a_page_idx() -> None:
    """A content_list with no usable page_idx counts no page."""
    assert MineruEngine._MineruEngine__page_count([{"page_idx": None}, {}]) == 0  # type: ignore[attr-defined]

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


def test_engine_retains_only_what_it_reads() -> None:
    """The weight hoster and cache root are accepted but never stored (MinerU reads them from env)."""
    engine = MineruEngine("vlm-transformers", "en", "huggingface", "/models")

    assert not hasattr(engine, "_model_source")
    assert not hasattr(engine, "_model_cache_home")
    assert engine.backend == "vlm-transformers"

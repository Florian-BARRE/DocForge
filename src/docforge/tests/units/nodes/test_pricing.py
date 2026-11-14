"""Model→price table: a known model computes cost = pt/1e6*in + ct/1e6*out, an unknown model
prices to None (so the UI shows tokens but a "—" cost, never a fabricated number), and zero tokens
on a known model is exactly 0.0. A paid embedding model (input tokens only) prices against
EMBED_PRICING at its single input rate."""

from shared_libs.pipelines.nodes import openai_compat
from shared_libs.pipelines.nodes.openai_compat import (
    EMBED_PRICING,
    MODEL_PRICING,
    OCR_PAGE_PRICING,
    price_usd,
)


def test_known_model_computes_input_plus_output() -> None:
    # gpt-4o-mini = (0.15, 0.60) USD / 1M tokens.
    cost = price_usd("gpt-4o-mini", 1_000_000, 2_000_000)
    assert cost == 0.15 + 2 * 0.60


def test_every_seeded_model_prices() -> None:
    for model in ("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"):
        assert model in MODEL_PRICING
        assert price_usd(model, 100, 100) is not None


def test_unknown_model_is_none_not_zero() -> None:
    assert price_usd("some-local-model", 1000, 1000) is None


def test_zero_tokens_on_a_known_model_is_zero() -> None:
    assert price_usd("gpt-4o", 0, 0) == 0.0


def test_paid_embed_model_prices_at_input_rate() -> None:
    # text-embedding-3-small = 0.02 USD / 1M tokens; an embed call has no completion side.
    assert price_usd("text-embedding-3-small", 1_000_000, 0) == 0.02


def test_every_seeded_embed_model_prices() -> None:
    for model, rate in EMBED_PRICING.items():
        assert price_usd(model, 2_000_000, 0) == 2 * rate


def test_unknown_embed_model_is_none() -> None:
    assert price_usd("local-embed-model", 5000, 0) is None


def test_ocr_page_pricing_lists_only_paid_kinds() -> None:
    # Hosted OCR bills per page: mistral is listed; the free local kinds are absent (priced 0 by
    # the estimator as known-local providers).
    assert OCR_PAGE_PRICING["mistral"] == 0.004
    for local_kind in ("rapidocr", "paddle", "tesseract"):
        assert local_kind not in OCR_PAGE_PRICING


def test_unused_per_page_helper_is_gone() -> None:
    # price_ocr_pages had no caller (the estimator reads OCR_PAGE_PRICING directly): removed (R-01).
    assert not hasattr(openai_compat, "price_ocr_pages")
    assert "price_ocr_pages" not in openai_compat.__all__

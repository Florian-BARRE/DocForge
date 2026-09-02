# ====== Code Summary ======
# Unit tests for PaddleOcrResponseNormalizer — the OCR-only sidecar's paddle-free logic
# (normalizer.py imports nothing but `typing` + `loggerplusplus`). This is the sole coverage that
# can prove the reading aggregation "would work" on this AVX-less CPU, where PaddlePaddle 3.x itself
# SIGILLs (exit 132) — see PADDLE-SIDECAR memory. Canned PaddleOCR `res` dicts stand in for real
# PaddleOCR.predict() output; both documented per-result shapes (dict item access — the pinned 3.7.0
# path — and object-attribute access, the defensive fallback) are exercised.

# ====== Standard Library Imports ======
from types import SimpleNamespace

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from libs.paddleocr.normalizer import PaddleOcrResponseNormalizer


def test_joins_lines_and_averages_confidences() -> None:
    """A single result's lines join with newlines and the confidence is the mean per-line score."""
    res = {"rec_texts": ["FACTURE 2024", "TOTAL 1500 EUR"], "rec_scores": [0.9, 0.8]}
    reading = PaddleOcrResponseNormalizer.to_reading([res])
    assert reading["text"] == "FACTURE 2024\nTOTAL 1500 EUR"
    assert reading["confidence"] == pytest.approx(0.85)


def test_aggregates_across_multiple_results() -> None:
    """Lines + scores are collected across every result in the predict() list, in order."""
    results = [
        {"rec_texts": ["page one"], "rec_scores": [1.0]},
        {"rec_texts": ["page two"], "rec_scores": [0.5]},
    ]
    reading = PaddleOcrResponseNormalizer.to_reading(results)
    assert reading["text"] == "page one\npage two"
    assert reading["confidence"] == pytest.approx(0.75)


def test_empty_reading_yields_zero_confidence() -> None:
    """A result with no recognized text degrades to empty text and 0.0 confidence, never a crash."""
    reading = PaddleOcrResponseNormalizer.to_reading([{"rec_texts": [], "rec_scores": []}])
    assert reading["text"] == ""
    assert reading["confidence"] == 0.0


def test_object_attribute_fallback_shape() -> None:
    """The defensive path: a result exposing rec_texts/rec_scores as attributes, not dict keys."""
    res = SimpleNamespace(rec_texts=["hello"], rec_scores=[0.6])
    reading = PaddleOcrResponseNormalizer.to_reading([res])
    assert reading["text"] == "hello"
    assert reading["confidence"] == 0.6


def test_missing_fields_contribute_nothing() -> None:
    """A malformed result missing both fields contributes no lines/scores rather than crashing."""
    reading = PaddleOcrResponseNormalizer.to_reading([{}])
    assert reading["text"] == ""
    assert reading["confidence"] == 0.0

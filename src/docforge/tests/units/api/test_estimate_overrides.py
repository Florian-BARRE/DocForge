"""EstimateOverrides validation: a per-collection cost override must reject nonsensical values —
negative rates and inf/nan — so a stored override can never poison the estimate (the earlier contract
constrained only the chat models' input/output, leaving embed/ocr dict values and inf unbounded).
The ``fastapi_app`` fixture registers app/ on sys.path so ``backend.*`` resolves."""

import pytest
from pydantic import ValidationError


def _model():
    from backend.libs.estimate.overrides import EstimateOverrides  # noqa: PLC0415

    return EstimateOverrides


def test_rejects_a_negative_embed_rate(fastapi_app) -> None:
    with pytest.raises(ValidationError):
        _model()(rates={"embed": {"text-embedding-3-small": -0.02}})


def test_rejects_a_negative_ocr_rate(fastapi_app) -> None:
    with pytest.raises(ValidationError):
        _model()(rates={"ocr": {"mistral": -1.0}})


def test_rejects_a_negative_model_input_rate(fastapi_app) -> None:
    with pytest.raises(ValidationError):
        _model()(rates={"models": {"gpt-4o": {"input": -1.0, "output": 2.0}}})


def test_rejects_an_infinite_assumption(fastapi_app) -> None:
    with pytest.raises(ValidationError):
        _model()(assumptions={"tokens_per_page": float("inf")})


def test_rejects_a_nan_rate(fastapi_app) -> None:
    with pytest.raises(ValidationError):
        _model()(rates={"embed": {"m": float("nan")}})


def test_accepts_a_valid_partial_override(fastapi_app) -> None:
    override = _model()(
        rates={"embed": {"m": 0.02}, "ocr": {"mistral": 1.0}},
        assumptions={"tokens_per_page": 500.0, "scanned_page_ratio": 0.3},
    )
    assert override.rates.embed == {"m": 0.02}
    assert override.assumptions.tokens_per_page == 500.0

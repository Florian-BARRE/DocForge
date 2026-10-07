"""Bulk-enqueue backpressure (429 + Retry-After) and the estimate-required gate (409)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException


def _admission(depth, max_depth=100):
    from backend.libs.admission import QueueAdmission  # noqa: PLC0415

    queue = MagicMock()
    queue.queue_depth = AsyncMock(
        side_effect=depth if isinstance(depth, Exception) else None,
        return_value=None if isinstance(depth, Exception) else depth,
    )
    return QueueAdmission(queue, max_depth=max_depth, retry_after_seconds=45)


async def test_bulk_under_limit_passes() -> None:
    await _admission(10).check_bulk(50)


async def test_bulk_over_limit_is_429_with_retry_after() -> None:
    with pytest.raises(HTTPException) as caught:
        await _admission(80).check_bulk(30)
    assert caught.value.status_code == 429
    assert caught.value.headers["Retry-After"] == "45"
    assert caught.value.detail["code"] == "queue_saturated"


async def test_disabled_and_unreadable_queue_fail_open() -> None:
    await _admission(10_000, max_depth=0).check_bulk(5)
    await _admission(RuntimeError("redis down")).check_bulk(5)


def _gate(threshold=200):
    from backend.libs.admission import ReingestEstimateGate  # noqa: PLC0415

    estimate = MagicMock(
        document_count=500,
        total_cost_usd=1.5,
        total_cost_lower_bound_usd=1.5,
        cost_complete=True,
        total_prompt_tokens=10,
        total_completion_tokens=2,
        caveats=["c"],
    )
    estimator = MagicMock()
    estimator.estimate = AsyncMock(return_value=estimate)
    return ReingestEstimateGate(estimator, threshold), estimator


async def test_estimate_required_above_threshold() -> None:
    gate, _ = _gate()
    with pytest.raises(HTTPException) as caught:
        await gate.require(uuid.uuid4(), 500, False, MagicMock())
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "estimate_required"
    assert caught.value.detail["estimate"]["total_cost_usd"] == 1.5


async def test_estimate_gate_passes_when_small_or_confirmed_or_disabled() -> None:
    gate, estimator = _gate()
    await gate.require(uuid.uuid4(), 200, False, MagicMock())
    await gate.require(uuid.uuid4(), 5000, True, MagicMock())
    await _gate(0)[0].require(uuid.uuid4(), 5000, False, MagicMock())
    estimator.estimate.assert_not_called()


def test_replay_summary_prices_only_the_replayed_stages() -> None:
    from types import SimpleNamespace  # noqa: PLC0415

    from backend.libs.admission import ReingestEstimateGate  # noqa: PLC0415

    def stage(name, cost, prompt):
        return SimpleNamespace(stage=name, cost_usd=cost, prompt_tokens=prompt, completion_tokens=1)

    estimate = SimpleNamespace(
        document_count=4,
        total_cost_usd=9.0,
        total_cost_lower_bound_usd=9.0,
        cost_complete=True,
        total_prompt_tokens=999,
        total_completion_tokens=5,
        stages=[
            stage("enrich_vlm", 4.0, 400),
            stage("contextualize", 3.0, 300),
            stage("metagen_document", 1.5, 150),
            stage("embed", 0.5, 50),
        ],
        caveats=[],
    )
    summary = ReingestEstimateGate.summarize(estimate, "metagen_document", technical=True)
    assert summary["priced_stages"] == ["metagen_document", "embed"]
    assert summary["total_cost_usd"] == 2.0
    assert summary["total_prompt_tokens"] == 200
    assert "replay_from=metagen_document" in summary["caveats"][-1]
    # A stage with an unknown rate makes the replay total incomplete (lower bound only).
    estimate.stages[-1].cost_usd = None
    partial = ReingestEstimateGate.summarize(estimate, "metagen_document", technical=True)
    assert partial["total_cost_usd"] is None and partial["total_cost_lower_bound_usd"] == 1.5
    assert partial["cost_complete"] is False


async def test_estimate_required_body_hides_technical_detail_without_read_technical() -> None:
    """M-2: the bulk routes need only WRITE — the 409 body must not leak models/providers/rate keys
    (caveats, priced stages, tokens) unless the caller holds READ_TECHNICAL."""
    gate, _ = _gate()
    estimate = MagicMock(
        document_count=500,
        total_cost_usd=1.5,
        total_cost_lower_bound_usd=1.5,
        cost_complete=True,
        total_prompt_tokens=10,
        total_completion_tokens=2,
        stages=[MagicMock(stage="embed")],
        caveats=["model bge-m3 via openai_compatible rate key embed:x"],
    )
    gate._estimator.estimate = AsyncMock(return_value=estimate)
    with pytest.raises(HTTPException) as caught:
        await gate.require(uuid.uuid4(), 500, False, MagicMock())
    public = caught.value.detail["estimate"]
    assert set(public) == {
        "document_count",
        "total_cost_usd",
        "total_cost_lower_bound_usd",
        "cost_complete",
    }
    assert caught.value.detail["threshold"] == 200
    with pytest.raises(HTTPException) as caught:
        await gate.require(uuid.uuid4(), 500, False, MagicMock(), technical=True)
    full = caught.value.detail["estimate"]
    assert full["caveats"] == estimate.caveats and full["priced_stages"] == ["embed"]

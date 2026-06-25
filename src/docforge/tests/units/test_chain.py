# ====== Code Summary ======
# Unit tests for the generalised Chain[T, R] + ChainGate primitives.
# Covers the four canonical scenarios listed in the Phase-A plan:
#   1. first provider succeeds — single attempt, no escalation
#   2. first escalates, second succeeds — two attempts, second is final
#   3. every provider escalates — exhausted, result is None
#   4. provider raises — counted as a failed attempt, chain moves on

# ====== Standard Library Imports ======
from __future__ import annotations

import pytest

# ====== Internal Project Imports ======
from common_libs.providers.chain import (
    Chain,
    ChainExhaustedError,
    ChainOutcome,
)
from common_libs.providers.chain_gate import ChainGate, ChainGateConfig


class _ScoredResult:
    """Test double — a tiny result type implementing ScoredResult."""

    def __init__(self, value: str, score: float | None) -> None:
        self.value = value
        self._score = score

    def score(self) -> float | None:
        return self._score


class _FakeProvider:
    """Test double — a provider with a ``name`` and a parameterised behaviour."""

    def __init__(
        self,
        name: str,
        result: _ScoredResult | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self.name = name
        self.version = "test"
        self._result = result
        self._raise = raise_exc
        self.call_count = 0

    async def run(self) -> _ScoredResult:
        self.call_count += 1
        if self._raise is not None:
            raise self._raise
        assert self._result is not None
        return self._result


def _gate(min_score: float) -> ChainGate:
    """Escalation-only gate for the legacy behavior tests.

    Uses failure_policy='continue' so an exhausted chain returns an empty outcome (the
    pre-CHUNK-2 contract these tests assert) instead of raising — the raise/continue policy
    itself is covered by the dedicated policy tests below.
    """
    return ChainGate(ChainGateConfig(min_score=min_score, failure_policy="continue"))


@pytest.mark.asyncio
async def test_first_provider_succeeds() -> None:
    """A high-scoring first provider returns immediately with a single attempt."""
    p1 = _FakeProvider("p1", result=_ScoredResult("ok", score=0.9))
    p2 = _FakeProvider("p2", result=_ScoredResult("never", score=0.95))
    chain = Chain(stage="test", providers=[p1, p2], gate=_gate(0.6))

    outcome = await chain.call(lambda p: p.run())

    assert outcome.succeeded
    assert outcome.result is not None and outcome.result.value == "ok"
    assert outcome.final_provider == "p1"
    assert len(outcome.attempts) == 1
    assert outcome.attempts[0].escalated is False
    assert p2.call_count == 0


@pytest.mark.asyncio
async def test_first_escalates_second_succeeds() -> None:
    """A low-scoring first attempt escalates to the second provider."""
    p1 = _FakeProvider("p1", result=_ScoredResult("low", score=0.3))
    p2 = _FakeProvider("p2", result=_ScoredResult("good", score=0.8))
    chain = Chain(stage="test", providers=[p1, p2], gate=_gate(0.5))

    outcome = await chain.call(lambda p: p.run())

    assert outcome.succeeded
    assert outcome.result is not None and outcome.result.value == "good"
    assert outcome.final_provider == "p2"
    assert len(outcome.attempts) == 2
    assert outcome.attempts[0].escalated is True
    assert outcome.attempts[1].escalated is False


@pytest.mark.asyncio
async def test_every_provider_escalates() -> None:
    """An exhausted chain returns ``ChainOutcome.result == None``."""
    p1 = _FakeProvider("p1", result=_ScoredResult("low1", score=0.1))
    p2 = _FakeProvider("p2", result=_ScoredResult("low2", score=0.2))
    chain = Chain(stage="test", providers=[p1, p2], gate=_gate(0.9))

    outcome = await chain.call(lambda p: p.run())

    assert outcome.result is None
    assert outcome.succeeded is False
    assert outcome.final_provider is None
    assert len(outcome.attempts) == 2
    assert all(a.escalated for a in outcome.attempts)


@pytest.mark.asyncio
async def test_provider_raises_then_recovers() -> None:
    """A raising provider is logged as a failed attempt; the chain tries the next."""
    p1 = _FakeProvider("p1", raise_exc=RuntimeError("kaboom"))
    p2 = _FakeProvider("p2", result=_ScoredResult("recovered", score=0.8))
    chain = Chain(stage="test", providers=[p1, p2], gate=_gate(0.5))

    outcome = await chain.call(lambda p: p.run())

    assert outcome.succeeded
    assert outcome.final_provider == "p2"
    assert outcome.attempts[0].succeeded is False
    assert outcome.attempts[0].error is not None
    assert "RuntimeError" in outcome.attempts[0].error
    assert outcome.attempts[1].succeeded is True


@pytest.mark.asyncio
async def test_unknown_score_is_treated_as_good_enough() -> None:
    """A result that returns ``score()=None`` does NOT trigger min_score escalation."""
    p1 = _FakeProvider("p1", result=_ScoredResult("unscored", score=None))
    p2 = _FakeProvider("p2", result=_ScoredResult("never", score=0.99))
    chain = Chain(stage="test", providers=[p1, p2], gate=_gate(0.9))

    outcome = await chain.call(lambda p: p.run())

    assert outcome.succeeded
    assert outcome.final_provider == "p1"
    assert p2.call_count == 0


@pytest.mark.asyncio
async def test_chain_signature_is_stable() -> None:
    """The signature is the comma-joined ``name:version`` for every provider, in order."""
    p1 = _FakeProvider("p1", result=_ScoredResult("a", score=0.9))
    p2 = _FakeProvider("p2", result=_ScoredResult("b", score=0.9))
    chain = Chain(stage="test", providers=[p1, p2], gate=_gate(0.5))

    assert chain.signature() == "p1:test,p2:test"
    assert chain.first_provider_name == "p1"


# ─── Failure policy: raise vs continue (CHUNK 2) ───────────────────────────────


def _policy_gate(
    min_score: float = 0.5,
    *,
    failure_policy: str = "raise",
    on_degraded: str = "empty",
    max_duration_ms: int | None = None,
) -> ChainGate:
    """Build a gate exercising the new failure-policy / time-gate knobs."""
    return ChainGate(
        ChainGateConfig(
            min_score=min_score,
            failure_policy=failure_policy,  # type: ignore[arg-type]
            on_degraded=on_degraded,  # type: ignore[arg-type]
            max_duration_ms=max_duration_ms,
        )
    )


@pytest.mark.asyncio
async def test_exhaustion_raises_chain_exhausted_error() -> None:
    """failure_policy='raise' (default) → exhaustion raises ChainExhaustedError with a precise msg."""
    p1 = _FakeProvider("docling", result=_ScoredResult("low", score=0.3))
    p2 = _FakeProvider("mineru", raise_exc=RuntimeError("boom"))
    chain = Chain(stage="parse", providers=[p1, p2], gate=_policy_gate(0.5, failure_policy="raise"))

    with pytest.raises(ChainExhaustedError) as excinfo:
        await chain.call(lambda p: p.run())

    err = excinfo.value
    assert err.stage == "parse"
    assert len(err.attempts) == 2
    msg = str(err)
    # Message names the stage, both providers, the below-threshold score and the error.
    assert "'parse' chain exhausted" in msg
    assert "docling(score=0.30" in msg
    assert "mineru(error=" in msg and "RuntimeError" in msg


@pytest.mark.asyncio
async def test_continue_empty_returns_degraded_none() -> None:
    """failure_policy='continue' + on_degraded='empty' → result None, degraded True, no raise."""
    p1 = _FakeProvider("p1", result=_ScoredResult("low1", score=0.1))
    p2 = _FakeProvider("p2", result=_ScoredResult("low2", score=0.2))
    chain = Chain(
        stage="ocr",
        providers=[p1, p2],
        gate=_policy_gate(0.9, failure_policy="continue", on_degraded="empty"),
    )

    outcome = await chain.call(lambda p: p.run())

    assert outcome.result is None
    assert outcome.degraded is True
    assert outcome.final_provider is None
    assert len(outcome.attempts) == 2


@pytest.mark.asyncio
async def test_continue_best_effort_returns_highest_below_threshold() -> None:
    """on_degraded='best_effort' → returns the highest-scoring SUCCEEDED below-threshold result."""
    p1 = _FakeProvider("p1", result=_ScoredResult("worse", score=0.2))
    p2 = _FakeProvider("p2", result=_ScoredResult("better", score=0.4))
    chain = Chain(
        stage="vlm",
        providers=[p1, p2],
        gate=_policy_gate(0.9, failure_policy="continue", on_degraded="best_effort"),
    )

    outcome = await chain.call(lambda p: p.run())

    assert outcome.degraded is True
    assert outcome.result is not None and outcome.result.value == "better"
    assert outcome.final_provider == "p2"


@pytest.mark.asyncio
async def test_continue_best_effort_falls_back_to_empty_when_all_error() -> None:
    """best_effort with NO succeeded result (all hard-errored) → degraded empty (result None)."""
    p1 = _FakeProvider("p1", raise_exc=RuntimeError("a"))
    p2 = _FakeProvider("p2", raise_exc=RuntimeError("b"))
    chain = Chain(
        stage="vlm",
        providers=[p1, p2],
        gate=_policy_gate(0.5, failure_policy="continue", on_degraded="best_effort"),
    )

    outcome = await chain.call(lambda p: p.run())

    assert outcome.degraded is True
    assert outcome.result is None
    assert outcome.final_provider is None


@pytest.mark.asyncio
async def test_accepted_result_is_not_degraded() -> None:
    """A normally-accepted result carries degraded=False under any failure policy."""
    p1 = _FakeProvider("p1", result=_ScoredResult("good", score=0.9))
    chain = Chain(
        stage="parse",
        providers=[p1],
        gate=_policy_gate(0.5, failure_policy="continue"),
    )

    outcome = await chain.call(lambda p: p.run())

    assert outcome.succeeded
    assert outcome.degraded is False


@pytest.mark.asyncio
async def test_duration_gate_escalates_slow_attempt() -> None:
    """max_duration_ms → an attempt slower than the budget escalates to the next provider."""

    class _SlowProvider:
        """Provider whose call sleeps long enough to exceed a tiny time budget."""

        def __init__(self, name: str, sleep_s: float, score: float) -> None:
            self.name = name
            self.version = "test"
            self._sleep_s = sleep_s
            self._score = score

        async def run(self) -> _ScoredResult:
            import asyncio

            await asyncio.sleep(self._sleep_s)
            return _ScoredResult(self.name, score=self._score)

    slow = _SlowProvider("slow", sleep_s=0.05, score=0.99)  # ~50ms > 1ms budget → escalate
    fast = _FakeProvider("fast", result=_ScoredResult("fast", score=0.6))
    chain = Chain(
        stage="parse",
        providers=[slow, fast],
        gate=_policy_gate(0.5, max_duration_ms=1),
    )

    outcome = await chain.call(lambda p: p.run())

    assert outcome.succeeded
    assert outcome.final_provider == "fast"
    assert outcome.attempts[0].escalated is True  # slow tripped the time gate
    assert outcome.attempts[1].escalated is False

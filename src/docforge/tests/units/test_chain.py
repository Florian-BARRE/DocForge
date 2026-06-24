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
from common_libs.providers.chain import Chain, ChainOutcome, ProviderChain
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

    cost_per_call = 0.0

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
    return ChainGate(ChainGateConfig(min_score=min_score))


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


# ─── Backward-compatibility wrapper ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_legacy_provider_chain_returns_raw_result() -> None:
    """The legacy wrapper preserves the pre-Phase-A ``raw result or None`` contract."""
    p1 = _FakeProvider("p1", result=_ScoredResult("low", score=0.3))
    p2 = _FakeProvider("p2", result=_ScoredResult("good", score=0.8))
    chain = ProviderChain(
        providers=[p1, p2],
        escalate_if=lambda r: r.score() < 0.5,
    )

    result = await chain.call(lambda p: p.run())
    assert result is not None and result.value == "good"


@pytest.mark.asyncio
async def test_legacy_provider_chain_exhaustion_returns_none() -> None:
    """The legacy wrapper still returns None when every provider escalates."""
    p1 = _FakeProvider("p1", result=_ScoredResult("low1", score=0.1))
    p2 = _FakeProvider("p2", result=_ScoredResult("low2", score=0.2))
    chain = ProviderChain(
        providers=[p1, p2],
        escalate_if=lambda r: r.score() < 0.9,
    )

    result = await chain.call(lambda p: p.run())
    assert result is None

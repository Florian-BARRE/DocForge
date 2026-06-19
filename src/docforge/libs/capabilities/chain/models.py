# ====== Code Summary ======
# Data models for the chain escalation primitive: per-attempt records and the
# per-chain outcome envelope.  Also contains the public helper that converts a
# ChainOutcome into the plain-dict shape expected by the IR layer.
#
# No I/O, no providers, no logging — pure frozen dataclasses and one free function.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

R = TypeVar("R")


# ─── Per-attempt and per-chain records ──────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ChainAttempt:
    """
    One attempt within a chain — what the provider did and how the gate reacted.

    Attributes:
        provider_id (str): Stable identifier of the provider that ran this attempt.
        score (float | None): The result's self-reported quality (see ScoredResult).
            None when the result type does not score or when the attempt raised.
        duration_ms (int): Wall-clock duration of the provider call.
        succeeded (bool): False when the provider raised or returned None.
        escalated (bool): True when the gate told the chain to try the next provider.
        error (str | None): The exception summary when the attempt raised.
        cost_usd (float): Provider-reported cost of this attempt (0.0 for free local
            backends).  Populated when the provider exposes ``cost_per_call``.
    """

    provider_id: str
    score: float | None
    duration_ms: int
    succeeded: bool
    escalated: bool
    error: str | None = None
    cost_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class ChainOutcome(Generic[R]):
    """
    The full record of a chain invocation: the final result + every attempt.

    Attributes:
        result (R | None): The first satisfactory result, or None when every provider
            either raised or was escalated.
        attempts (list[ChainAttempt]): One entry per provider tried, in order.
        final_provider (str | None): provider_id of the attempt whose result was
            returned, or None when the chain exhausted without success.
    """

    result: R | None
    attempts: list[ChainAttempt] = field(default_factory=list)
    final_provider: str | None = None

    @property
    def succeeded(self) -> bool:
        """True when the chain produced a usable result."""
        return self.result is not None

    @property
    def total_duration_ms(self) -> int:
        """Sum of every attempt's duration — useful for stage-level logging."""
        return sum(a.duration_ms for a in self.attempts)


# ─── Public helper (IR boundary) ────────────────────────────────────────────


def chain_outcome_to_attempt_dicts(outcome: "ChainOutcome[Any]") -> list[dict[str, Any]]:
    """
    Convert a ``ChainOutcome`` into the plain-dict shape ``ChainTraceIR.attempts`` expects.

    The IR layer does not import the providers package; constructing
    ``ChainAttemptIR(**dict)`` at the call site keeps the two layers decoupled.

    Args:
        outcome (ChainOutcome): The chain invocation record.

    Returns:
        list[dict[str, Any]]: One dict per attempt, matching the IR ChainAttemptIR fields.
    """
    return [
        {
            "provider_id": a.provider_id,
            "score": a.score,
            "duration_ms": a.duration_ms,
            "succeeded": a.succeeded,
            "escalated": a.escalated,
            "error": a.error,
            "cost_usd": a.cost_usd,
        }
        for a in outcome.attempts
    ]


# ─── Internal helpers ────────────────────────────────────────────────────────


def _replace_escalated(attempt: ChainAttempt, escalated: bool) -> ChainAttempt:
    """Build a copy of ``attempt`` with the escalated flag set — frozen dataclass."""
    return ChainAttempt(
        provider_id=attempt.provider_id,
        score=attempt.score,
        duration_ms=attempt.duration_ms,
        succeeded=attempt.succeeded,
        escalated=escalated,
        error=attempt.error,
        cost_usd=attempt.cost_usd,
    )


def _default_provider_id(provider: Any) -> str:
    """Best-effort stable id: ``.name`` attribute, else repr."""
    return str(getattr(provider, "name", None) or repr(provider))


def _fmt_score(score: float | None) -> str:
    """Compact score formatting for log lines (``unknown`` when None)."""
    return "unknown" if score is None else f"{score:.3f}"

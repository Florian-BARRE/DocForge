# ====== Code Summary ======
# Data models for the chain escalation primitive: per-attempt records and the
# per-chain outcome envelope.  Also contains ChainHelpers, a static-only class
# grouping the internal manipulation utilities and the public IR-boundary converter.
#
# No I/O, no providers, no logging — pure frozen dataclasses and static helpers.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field
from typing import Any

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
    """

    provider_id: str
    score: float | None
    duration_ms: int
    succeeded: bool
    escalated: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ChainOutcome[R]:
    """
    The full record of a chain invocation: the final result + every attempt.

    Attributes:
        result (R | None): The first satisfactory result, or None when every provider
            either raised or was escalated.  A ``best_effort`` degraded outcome carries
            the highest-scoring below-threshold result here (with ``degraded=True``).
        attempts (list[ChainAttempt]): One entry per provider tried, in order.
        final_provider (str | None): provider_id of the attempt whose result was
            returned, or None when the chain exhausted without success.
        degraded (bool): True when the chain exhausted under ``failure_policy="continue"``
            and returned a degraded outcome (empty or best-effort) instead of raising.
            A normally-accepted result always has ``degraded=False``.
    """

    result: R | None
    attempts: list[ChainAttempt] = field(default_factory=list)
    final_provider: str | None = None
    degraded: bool = False

    @property
    def succeeded(self) -> bool:
        """True when the chain produced a usable result."""
        return self.result is not None

    @property
    def total_duration_ms(self) -> int:
        """Sum of every attempt's duration — useful for stage-level logging."""
        return sum(a.duration_ms for a in self.attempts)


# ─── Static helpers ──────────────────────────────────────────────────────────


class ChainHelpers:
    """
    Static utility helpers for the chain escalation primitive.

    Groups the IR-boundary converter (public) and the internal manipulation
    utilities used by Chain[T, R].  No instance state — instantiation is blocked.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        raise TypeError("ChainHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def chain_outcome_to_attempt_dicts(outcome: "ChainOutcome[Any]") -> list[dict[str, Any]]:
        """
        Convert a ``ChainOutcome`` into the plain-dict shape ``ChainTrace.attempts`` expects.

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
            }
            for a in outcome.attempts
        ]

    @staticmethod
    def replace_escalated(attempt: ChainAttempt, escalated: bool) -> ChainAttempt:
        """
        Build a copy of ``attempt`` with the escalated flag overridden.

        Required because ``ChainAttempt`` is a frozen dataclass — fields cannot be
        mutated in place; a new instance must be constructed.

        Args:
            attempt (ChainAttempt): The original attempt record.
            escalated (bool): The new value for the escalated flag.

        Returns:
            ChainAttempt: A new frozen instance identical to ``attempt`` except for
                the ``escalated`` field.
        """
        return ChainAttempt(
            provider_id=attempt.provider_id,
            score=attempt.score,
            duration_ms=attempt.duration_ms,
            succeeded=attempt.succeeded,
            escalated=escalated,
            error=attempt.error,
        )

    @staticmethod
    def gate_tripped(outcome: "ChainOutcome[Any]") -> str | None:
        """
        Infer which gate caused the final escalation on a degraded/exhausted outcome.

        Inspects the LAST attempt (the one that ultimately failed the chain):
        an attempt that raised -> ``"error"``; a scored attempt -> ``"score"``; a
        succeeded-but-escalated attempt with no score -> ``"time"`` (only the time gate
        can reject a scoreless success). Returns None when there are no attempts.

        Args:
            outcome (ChainOutcome[Any]): The chain invocation record.

        Returns:
            str | None: ``"error"`` | ``"score"`` | ``"time"`` | None.
        """
        if not outcome.attempts:
            return None
        last = outcome.attempts[-1]
        if not last.succeeded:
            return "error"
        if last.score is not None:
            return "score"
        return "time"

    @staticmethod
    def default_provider_id(provider: Any) -> str:
        """
        Best-effort stable identifier for a provider instance.

        Prefers the ``.name`` attribute when present; falls back to ``repr(provider)``
        so every provider always yields a non-empty string.

        Args:
            provider (Any): Any provider instance.

        Returns:
            str: A stable, non-empty identifier string.
        """
        return str(getattr(provider, "name", None) or repr(provider))

    @staticmethod
    def fmt_score(score: float | None) -> str:
        """
        Compact score formatting for structured log lines.

        Args:
            score (float | None): The quality score, or None when unavailable.

        Returns:
            str: ``"unknown"`` when ``score`` is None, otherwise ``"{score:.3f}"``.
        """
        return "unknown" if score is None else f"{score:.3f}"


# ─── Public module-level alias (backward compatibility) ──────────────────────

# Exported from chain/__init__.py — callers that import chain_outcome_to_attempt_dicts
# directly from this module continue to work without modification.
chain_outcome_to_attempt_dicts = ChainHelpers.chain_outcome_to_attempt_dicts

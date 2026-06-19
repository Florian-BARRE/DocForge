# ====== Code Summary ======
# TraceHelpers — static factory methods for building ChainTrace IR objects used in S2.
# Covers three cases: a genuine chain outcome, a provider-call cache hit, and a skipped stage.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

from libs.capabilities.chain import ChainOutcome, chain_outcome_to_attempt_dicts

# ====== Internal Project Imports ======
from libs.core.ir.models import ChainAttemptIR, ChainTrace


class TraceHelpers:
    """
    Static factory helpers for constructing ``ChainTrace`` IR objects in S2.

    Three trace shapes are needed:
    - ``from_outcome`` — converts a real ``ChainOutcome`` to a ``ChainTrace``.
    - ``cache_hit`` — synthetic trace for a provider-call cache hit (zero cost, zero latency).
    - ``skip`` — synthetic trace for a sub-stage that was bypassed (no chain / no provider).
    """

    logger = loggerplusplus.bind(identifier="TraceHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[return]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError(f"{cls.__name__} is a static-only class and cannot be instantiated.")

    @staticmethod
    def from_outcome(stage: str, outcome: ChainOutcome[Any]) -> ChainTrace:
        """
        Convert a ``ChainOutcome`` into the IR ``ChainTrace`` serialisation.

        Args:
            stage (str): Stage label (e.g. ``"ocr"``, ``"vlm"``, ``"classifier"``).
            outcome (ChainOutcome[Any]): The result returned by ``Chain.call()``.

        Returns:
            ChainTrace: Populated trace with one attempt per provider tried.
        """
        return ChainTrace(
            stage=stage,
            attempts=[
                ChainAttemptIR(**d) for d in chain_outcome_to_attempt_dicts(outcome)
            ],
            final_provider=outcome.final_provider,
        )

    @classmethod
    def cache_hit(cls, stage: str, provider_id: str, call_fp: str) -> ChainTrace:
        """
        Build a synthetic ``ChainTrace`` describing a provider-call cache hit.

        The cache is modelled as a degenerate "provider" so the existing UI does not
        need a new shape: one attempt with ``provider_id="provider_cache"``, a success
        badge, ``duration=0``, ``cost=0``.  The original chain's first provider id is
        carried in the attempt's ``error`` slot so operators can see
        "cache hit — would have called <original_provider>".

        Args:
            stage (str): Stage label (e.g. ``"ocr"``).
            provider_id (str): The provider that *would* have been called (for display).
            call_fp (str): Full provider-call fingerprint (first 12 chars shown in UI).

        Returns:
            ChainTrace: Synthetic trace representing the cache hit.
        """
        cls.logger.debug(
            f"TraceHelpers.cache_hit: stage={stage} provider={provider_id} fp={call_fp[:12]}…"
        )
        return ChainTrace(
            stage=stage,
            attempts=[
                ChainAttemptIR(
                    provider_id="provider_cache",
                    score=1.0,
                    duration_ms=0,
                    succeeded=True,
                    escalated=False,
                    error=(
                        f"cache hit — would have called {provider_id} "
                        f"(fp={call_fp[:12]}…)"
                    ),
                    cost_usd=0.0,
                )
            ],
            final_provider="provider_cache",
        )

    @staticmethod
    def skip(stage: str, reason: str) -> ChainTrace:
        """
        Build a ``ChainTrace`` describing a sub-stage that was skipped.

        Used when there is no chain configured for a capability, or when the chain
        has no providers.

        Args:
            stage (str): Stage label (e.g. ``"ocr"``).
            reason (str): Human-readable reason for skipping (e.g. ``"no chain"``).

        Returns:
            ChainTrace: Synthetic trace with a single "skip" attempt.
        """
        return ChainTrace(
            stage=stage,
            attempts=[
                ChainAttemptIR(
                    provider_id="skip",
                    score=None,
                    duration_ms=0,
                    succeeded=False,
                    escalated=False,
                    error=reason,
                    cost_usd=0.0,
                )
            ],
            final_provider=None,
        )


# ------------------- Public API ------------------- #
__all__ = ["TraceHelpers"]

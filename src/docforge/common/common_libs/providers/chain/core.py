# ====== Code Summary ======
# Chain[T, R] — the generic ordered provider escalation engine.
#
# Dispatches calls to providers in declaration order, consulting the ChainGate
# policy after each attempt.  Returns a ChainOutcome carrying the final result
# and the full per-attempt audit log.  Thread-safe: no mutable state beyond the
# immutable provider list set at construction time.
#
# Per-attempt execution, score extraction, and log emission are delegated to
# ChainRunHelpers (run_helpers.py) to keep this file under 200 lines.

# ====== Standard Library Imports ======
from __future__ import annotations

from collections.abc import Awaitable, Callable

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.providers.chain_gate import ChainGate

# ====== Local Project Imports ======
from .errors import ChainExhaustedError
from .models import ChainAttempt, ChainHelpers, ChainOutcome
from .run_helpers import ChainRunHelpers


class Chain[T, R](LoggerClass):
    """
    Ordered provider chain with policy-driven escalation and full provenance capture.

    Each call dispatches to providers in declaration order.  After each attempt the
    chain consults the ``ChainGate`` policy — if the gate signals escalation, the
    next provider is tried; otherwise the result is returned wrapped in a
    ``ChainOutcome`` carrying the full attempt log.

    Example::

        gate = ChainGate(ChainGateConfig(min_score=0.6))
        chain = Chain(
            stage="parse",
            providers=[docling, mineru, marker],
            gate=gate,
        )
        outcome = await chain.call(lambda p: p.parse(pdf_bytes, doc_id, src_hash))
        if outcome.succeeded:
            ir = outcome.result
            ir.chain_traces.append(ChainTrace(stage="parse", attempts=outcome.attempts))
    """

    def __init__(
        self,
        stage: str,
        providers: list[T],
        gate: ChainGate,
        provider_id: Callable[[T], str] | None = None,
    ) -> None:
        """
        Initialise the chain.

        Args:
            stage (str): Human label of the stage this chain serves ("parse",
                "ocr", "vlm", "classifier", "embed").  Appears in every log line so
                operators can grep one stage's chain decisions.
            providers (list[T]): Ordered provider instances; index 0 is tried first.
            gate (ChainGate): Escalation policy applied after every attempt.
            provider_id (Callable[[T], str] | None): How to extract a stable id from
                a provider instance.  Defaults to ``getattr(p, "name", repr(p))``.
        """
        LoggerClass.__init__(self)
        self._stage = stage
        self._providers: list[T] = providers
        self._gate = gate
        self._provider_id: Callable[[T], str] = provider_id or ChainHelpers.default_provider_id

    @property
    def stage(self) -> str:
        """Stage label used in log lines and traces."""
        return self._stage

    @property
    def providers(self) -> list[T]:
        """Read-only access to the ordered provider list."""
        return self._providers

    @property
    def gate(self) -> ChainGate:
        """Read-only access to the escalation policy."""
        return self._gate

    @property
    def first_provider_name(self) -> str:
        """Identifier of the first (preferred) provider — kept for fingerprinting."""
        if not self._providers:
            return "none"
        return self._provider_id(self._providers[0])

    def signature(self) -> str:
        """
        Comma-joined ``id:version`` signature for the whole chain — used in fingerprints.

        Returns:
            str: Stable signature like ``"docling:1.0,mineru:0.3"`` covering every
                provider in declaration order.
        """
        parts: list[str] = []
        for p in self._providers:
            pid = self._provider_id(p)
            version = getattr(p, "version", "0")
            parts.append(f"{pid}:{version}")
        return ",".join(parts)

    async def call(self, fn: Callable[[T], Awaitable[R]]) -> ChainOutcome[R]:
        """
        Invoke ``fn`` on each provider in order until the gate stops escalation.

        Args:
            fn (Callable[[T], Awaitable[R]]): Coroutine factory receiving the current
                provider instance.  Example::

                    await chain.call(lambda p: p.extract(img, hint))

        Returns:
            ChainOutcome[R]: The first satisfactory result + every attempt's record
                (provider id, score, duration, escalated flag, error).  On exhaustion
                under ``failure_policy="continue"`` a degraded outcome is returned
                (``degraded=True``); under ``failure_policy="raise"`` it raises.

        Raises:
            ChainExhaustedError: When the chain is exhausted (no provider accepted) AND
                the gate's ``failure_policy`` is ``"raise"`` (the default).
        """
        attempts: list[ChainAttempt] = []
        total = len(self._providers)
        # Track the best (highest-scoring) SUCCEEDED-but-escalated result for best_effort.
        best_result: R | None = None
        best_score: float = float("-inf")
        best_provider: str | None = None

        # 1. Iterate providers in declaration order, recording one attempt each.
        for idx, provider in enumerate(self._providers, start=1):
            provider_id = self._provider_id(provider)
            attempt, raw_result = await ChainRunHelpers.run_attempt(provider, fn, provider_id)
            ChainRunHelpers.log_attempt(self.logger, self._stage, idx, total, attempt)

            # 2. The gate decides whether the chain stops or escalates.
            should_escalate = self._gate.should_escalate(raw_result, attempt)
            attempts.append(ChainHelpers.replace_escalated(attempt, should_escalate))

            if not should_escalate:
                self.logger.info(
                    f"[CHAIN {self._stage}] outcome provider={attempt.provider_id} "
                    f"attempts={len(attempts)} total_duration_ms="
                    f"{sum(a.duration_ms for a in attempts)}"
                )
                return ChainOutcome(
                    result=raw_result,
                    attempts=attempts,
                    final_provider=attempt.provider_id,
                    degraded=False,
                )

            # 3. Escalated — remember the best succeeded result for a possible best_effort fallback.
            if attempt.succeeded and raw_result is not None:
                score = attempt.score if attempt.score is not None else float("-inf")
                if best_result is None or score > best_score:
                    best_result, best_score, best_provider = raw_result, score, provider_id

        # 4. Every provider escalated or raised — apply the gate's failure policy.
        return self._on_exhausted(attempts, best_result, best_provider)

    def _on_exhausted(
        self,
        attempts: list[ChainAttempt],
        best_result: R | None,
        best_provider: str | None,
    ) -> ChainOutcome[R]:
        """
        Apply the gate's failure policy when the chain produced no accepted result.

        Args:
            attempts (list[ChainAttempt]): Every attempt made, in order.
            best_result (R | None): Highest-scoring SUCCEEDED-but-escalated result, if any.
            best_provider (str | None): provider_id that produced ``best_result``.

        Returns:
            ChainOutcome[R]: A degraded outcome (``failure_policy="continue"``).

        Raises:
            ChainExhaustedError: When ``failure_policy="raise"`` (the default).
        """
        policy = self._gate.config.failure_policy
        total = len(self._providers)

        # 1. raise → fail-closed: the worker boundary records the precise reason on the doc.
        if policy == "raise":
            self.logger.warning(
                f"[CHAIN {self._stage}] exhausted ({total} provider(s)) — policy=raise"
            )
            raise ChainExhaustedError(self._stage, attempts)

        # 2. continue + best_effort → return the best below-threshold succeeded result, if any.
        if self._gate.config.on_degraded == "best_effort" and best_result is not None:
            self.logger.warning(
                f"[CHAIN {self._stage}] exhausted — policy=continue on_degraded=best_effort "
                f"→ using below-threshold result from {best_provider}"
            )
            return ChainOutcome(
                result=best_result,
                attempts=attempts,
                final_provider=best_provider,
                degraded=True,
            )

        # 3. continue + empty (or best_effort with no succeeded result) → empty degraded outcome.
        self.logger.warning(
            f"[CHAIN {self._stage}] exhausted ({total} provider(s)) — "
            f"policy=continue on_degraded={self._gate.config.on_degraded} → degraded (empty)"
        )
        return ChainOutcome(result=None, attempts=attempts, final_provider=None, degraded=True)

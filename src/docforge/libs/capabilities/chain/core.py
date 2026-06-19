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
from libs.capabilities.chain_gate import ChainGate

# ====== Local Project Imports ======
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
                (provider id, score, duration, escalated flag, error, cost).
        """
        attempts: list[ChainAttempt] = []
        total = len(self._providers)

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
                )

        # 3. Every provider escalated or raised — the caller gets an empty outcome.
        self.logger.warning(
            f"[CHAIN {self._stage}] exhausted — {total} provider(s) escalated or raised"
        )
        return ChainOutcome(result=None, attempts=attempts, final_provider=None)

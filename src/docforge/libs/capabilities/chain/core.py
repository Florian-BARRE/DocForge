# ====== Code Summary ======
# Chain[T, R] — the generic ordered provider escalation engine.
#
# Dispatches calls to providers in declaration order, consulting the ChainGate
# policy after each attempt.  Returns a ChainOutcome carrying the final result
# and the full per-attempt audit log.  Thread-safe: no mutable state beyond the
# immutable provider list set at construction time.

# ====== Standard Library Imports ======
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Generic, TypeVar

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.capabilities.chain_gate import ChainGate

# ====== Local Project Imports ======
from .models import (
    ChainAttempt,
    ChainOutcome,
    _default_provider_id,
    _fmt_score,
    _replace_escalated,
)

T = TypeVar("T")
R = TypeVar("R")


class Chain(LoggerClass, Generic[T, R]):
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
        self._provider_id: Callable[[T], str] = provider_id or _default_provider_id

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
            attempt, raw_result = await self._run_attempt(provider, fn)
            self._log_attempt(idx, total, attempt)

            # 2. The gate decides whether the chain stops or escalates.
            should_escalate = self._gate.should_escalate(raw_result, attempt)
            attempts.append(_replace_escalated(attempt, should_escalate))

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

    async def _run_attempt(
        self,
        provider: T,
        fn: Callable[[T], Awaitable[R]],
    ) -> tuple[ChainAttempt, R | None]:
        """
        Execute a single provider call, timing it and capturing any exception.

        Returns the attempt record alongside the raw result so the gate can inspect
        it.  Returning a tuple (instead of stashing it on the chain instance) is
        what keeps ``Chain.call`` safe to invoke concurrently.

        Args:
            provider (T): Provider instance to invoke.
            fn (Callable[[T], Awaitable[R]]): The user's coroutine factory.

        Returns:
            tuple[ChainAttempt, R | None]: The attempt record (escalated flag is set
                later by the caller) and the raw result (None when the call raised).
        """
        provider_id = self._provider_id(provider)
        cost = float(getattr(provider, "cost_per_call", 0.0) or 0.0)
        start = time.perf_counter()
        try:
            # 1. Run the provider's coroutine; record the duration in either branch.
            result = await fn(provider)
            duration_ms = int((time.perf_counter() - start) * 1000)
            score = self._extract_score(result)
            return (
                ChainAttempt(
                    provider_id=provider_id,
                    score=score,
                    duration_ms=duration_ms,
                    succeeded=result is not None,
                    escalated=False,
                    error=None,
                    cost_usd=cost,
                ),
                result,
            )
        except Exception as exc:  # noqa: BLE001 — any failure escalates to the next provider
            # 2. Capture the exception summary; the gate will mark it as escalated.
            duration_ms = int((time.perf_counter() - start) * 1000)
            return (
                ChainAttempt(
                    provider_id=provider_id,
                    score=None,
                    duration_ms=duration_ms,
                    succeeded=False,
                    escalated=False,
                    error=f"{type(exc).__name__}: {exc}",
                    cost_usd=cost,
                ),
                None,
            )

    @staticmethod
    def _extract_score(result: Any) -> float | None:
        """
        Pull score off a ScoredResult; return None when the type doesn't score.

        The import is deferred inside the method to avoid a circular dependency:
        scoring.py → (nothing in chain/); chain/ → chain_gate.py → scoring.py.
        A top-level import of ScoredResult here would create a cycle through
        chain_gate.py which already imports scoring.py at module level.
        """
        from libs.capabilities.scoring import ScoredResult  # deferred — avoids cycle

        if isinstance(result, ScoredResult):
            try:
                return result.score()
            except Exception:  # noqa: BLE001 — never let a buggy score() break the chain
                return None
        return None

    def _log_attempt(self, idx: int, total: int, attempt: ChainAttempt) -> None:
        """Emit one structured log line per attempt (operator-readable)."""
        if attempt.succeeded:
            self.logger.info(
                f"[CHAIN {self._stage}] attempt {idx}/{total} "
                f"provider={attempt.provider_id} "
                f"score={_fmt_score(attempt.score)} "
                f"duration_ms={attempt.duration_ms}"
            )
        else:
            self.logger.warning(
                f"[CHAIN {self._stage}] attempt {idx}/{total} "
                f"provider={attempt.provider_id} FAILED "
                f"duration_ms={attempt.duration_ms} error={attempt.error!r}"
            )

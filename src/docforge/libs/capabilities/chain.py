# ====== Code Summary ======
# Generic provider chain with ordered escalation and full attempt-level provenance.
#
# ``Chain[T, R]`` is the single primitive every pipeline stage uses to try multiple
# providers in sequence: parser, classifier, OCR, VLM, embedder.  Each attempt is
# timed, scored (via ``ScoredResult.score()``), and gated by a ``ChainGate`` policy.
# The full attempt log is returned to the caller as a ``ChainOutcome`` so the IR can
# carry the lineage of which providers produced what.
#
# A thin ``ProviderChain[T]`` backward-compat wrapper is kept for callers that still
# expect the legacy "raw result or None" return signature (OCR + VLM in S2 today);
# new callers should consume ``ChainOutcome`` directly.

# ====== Standard Library Imports ======
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, TypeVar

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.capabilities.chain_gate import ChainGate, ChainGateConfig

T = TypeVar("T")
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


# ─── The generic chain ──────────────────────────────────────────────────────


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
        """Pull score off a ScoredResult; return None when the type doesn't score."""
        from libs.capabilities.scoring import ScoredResult
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


# ─── Public helpers (IR boundary) ───────────────────────────────────────────


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


# ─── Internal helpers ───────────────────────────────────────────────────────


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


# ─── Backward-compatibility wrapper ─────────────────────────────────────────


class ProviderChain(LoggerClass, Generic[T]):
    """
    Legacy wrapper preserving the pre-Phase-A "raw result or None" return shape.

    Existing callers in ``S2EnrichStage`` (OCR + VLM) use ``ProviderChain.call(fn)``
    and expect to receive the raw result (or None).  This adapter wires the legacy
    ``escalate_if`` predicate through a synthetic ``ChainGate`` so behaviour is
    bit-identical while the new ``ChainOutcome`` plumbing rolls out elsewhere.

    New callers should construct ``Chain[T, R]`` directly.
    """

    def __init__(
        self,
        providers: list[T],
        escalate_if: Callable[[Any], bool],
        stage: str = "legacy",
    ) -> None:
        """
        Initialise the legacy wrapper.

        Args:
            providers (list[T]): Ordered provider instances.
            escalate_if (Callable[[Any], bool]): Legacy predicate on the raw result;
                returns True when the next provider should be tried.
            stage (str): Optional stage label propagated into log lines.
        """
        LoggerClass.__init__(self)
        gate = _PredicateGate(escalate_if)
        self._inner: Chain[T, Any] = Chain(
            stage=stage,
            providers=providers,
            gate=gate,  # type: ignore[arg-type]  — _PredicateGate ducks ChainGate
        )

    @property
    def providers(self) -> list[T]:
        """Read-only access to the ordered provider list."""
        return self._inner.providers

    @property
    def first_provider_name(self) -> str:
        """Identifier of the first provider — kept for fingerprinting compatibility."""
        return self._inner.first_provider_name

    def provider_chain_signature(self) -> str:
        """Comma-joined ``name:version`` signature for fingerprinting — unchanged."""
        return self._inner.signature()

    async def call(self, fn: Callable[[T], Awaitable[Any]]) -> Any | None:
        """
        Invoke ``fn`` on each provider in order and return the raw result.

        Args:
            fn (Callable[[T], Awaitable[Any]]): Coroutine factory.

        Returns:
            Any | None: First satisfactory result, or None when the chain exhausts.
        """
        outcome = await self._inner.call(fn)
        return outcome.result


class _PredicateGate:
    """
    Adapt a legacy ``escalate_if(result) -> bool`` predicate to the ChainGate shape.

    Used only by ``ProviderChain`` so the legacy callers keep working while the
    typed-gate plumbing lands across the codebase.  Once every caller uses
    ``ChainGateConfig`` directly, this adapter can be deleted.
    """

    def __init__(self, predicate: Callable[[Any], bool]) -> None:
        self._predicate = predicate
        # Synthetic config — never actually consulted, kept for the API shape.
        self._cfg = ChainGateConfig()

    @property
    def config(self) -> ChainGateConfig:
        """Synthetic config (never consulted by the predicate path)."""
        return self._cfg

    def should_escalate(self, result: Any, attempt: ChainAttempt) -> bool:
        """Apply the legacy predicate; failed attempts always escalate."""
        if not attempt.succeeded:
            return True
        try:
            return bool(self._predicate(result))
        except Exception:  # noqa: BLE001 — match legacy fail-safe behaviour
            return True

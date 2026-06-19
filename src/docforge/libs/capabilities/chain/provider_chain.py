# ====== Code Summary ======
# ProviderChain — backward-compatibility wrapper preserving the pre-Phase-A
# "raw result or None" return shape for existing S2EnrichStage callers.
#
# Also houses _PredicateGate, the internal adapter that converts a legacy
# ``escalate_if(result) -> bool`` predicate into the ChainGate duck-type
# required by Chain[T, R].  Once every caller migrates to ChainGateConfig,
# _PredicateGate can be removed.

# ====== Standard Library Imports ======
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.capabilities.chain_gate import ChainGateConfig

# ====== Local Project Imports ======
from .core import Chain
from .models import ChainAttempt


class _PredicateGate:
    """
    Adapt a legacy ``escalate_if(result) -> bool`` predicate to the ChainGate shape.

    Used only by ``ProviderChain`` so the legacy callers keep working while the
    typed-gate plumbing lands across the codebase.  Once every caller uses
    ``ChainGateConfig`` directly, this adapter can be deleted.
    """

    def __init__(self, predicate: Callable[[Any], bool]) -> None:
        """
        Initialise the predicate adapter.

        Args:
            predicate (Callable[[Any], bool]): Legacy predicate on the raw result;
                returns True when the next provider should be tried.
        """
        self._predicate = predicate
        # Synthetic config — never actually consulted, kept for the API shape.
        self._cfg = ChainGateConfig()

    @property
    def config(self) -> ChainGateConfig:
        """Synthetic config (never consulted by the predicate path)."""
        return self._cfg

    def should_escalate(self, result: Any, attempt: ChainAttempt) -> bool:
        """
        Apply the legacy predicate; failed attempts always escalate.

        Args:
            result (Any): The provider's raw result.
            attempt (ChainAttempt): The attempt record from the chain.

        Returns:
            bool: True when the chain should try the next provider.
        """
        # 1. Failed attempts always escalate regardless of the predicate.
        if not attempt.succeeded:
            return True
        # 2. Delegate to the legacy predicate for scored results.
        try:
            return bool(self._predicate(result))
        except Exception:  # noqa: BLE001 — match legacy fail-safe behaviour
            return True


class ProviderChain[T](LoggerClass):
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
        """
        Comma-joined ``name:version`` signature for fingerprinting — unchanged.

        Returns:
            str: Stable provider chain signature string.
        """
        return self._inner.signature()

    async def call(self, fn: Callable[[T], Awaitable[Any]]) -> Any | None:
        """
        Invoke ``fn`` on each provider in order and return the raw result.

        Args:
            fn (Callable[[T], Awaitable[Any]]): Coroutine factory.

        Returns:
            Any | None: First satisfactory result, or None when the chain exhausts.
        """
        # 1. Delegate to the inner Chain and unwrap the raw result.
        outcome = await self._inner.call(fn)
        return outcome.result

# ====== Code Summary ======
# ProviderChain — backward-compatibility wrapper preserving the pre-Phase-A
# "raw result or None" return shape for existing S2EnrichStage callers.
#
# _PredicateGate (the legacy-predicate adapter) lives in predicate_gate.py;
# it is imported here so ProviderChain can wire it into the inner Chain.
# Once every caller migrates to ChainGateConfig, both can be removed.

# ====== Standard Library Imports ======
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .core import Chain
from .predicate_gate import _PredicateGate


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

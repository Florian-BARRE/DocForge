# ====== Code Summary ======
# _PredicateGate — internal adapter converting a legacy ``escalate_if(result) -> bool``
# predicate into the ChainGate duck-type expected by Chain[T, R].
#
# Isolated from ProviderChain so each file has a single class responsibility.
# Once every caller migrates to ChainGateConfig, this adapter can be removed.

# ====== Standard Library Imports ======
from __future__ import annotations

from collections.abc import Callable
from typing import Any

# ====== Internal Project Imports ======
from libs.capabilities.chain_gate import ChainGateConfig

# ====== Local Project Imports ======
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

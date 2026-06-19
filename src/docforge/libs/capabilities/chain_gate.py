# ====== Code Summary ======
# ChainGate — the escalation policy used by ``Chain[T, R]`` to decide whether the next
# provider should be tried after an attempt.
#
# The gate is a pure function over the (result, attempt) pair: no I/O, no provider
# internals.  It is configured by a typed ``ChainGateConfig`` so the discovery payload
# can expose every knob to the UI as scalar overlays.
#
# Today the only enforced criterion is ``min_score``.  ``max_duration_ms`` and
# ``max_cost_usd`` are accepted in the config so the UI surfaces them, but they are
# advisory in Phase A (no enforcement) — the wiring is reserved for Phase B.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Internal Project Imports ======
from libs.capabilities.scoring import ScoredResult

# ====== Local Project Imports ======
if TYPE_CHECKING:
    from libs.capabilities.chain import ChainAttempt


class ChainGateConfig(BaseModel):
    """
    Typed configuration for a chain's escalation policy.

    Attributes:
        min_score (float): Lower bound on the result's ``score()``.  An attempt whose
            score is strictly less than this triggers escalation.  A score of ``None``
            (unknown) never triggers escalation on its own.
        max_duration_ms (int | None): Soft upper bound on an attempt's wall-clock
            duration — surfaced in the UI for future enforcement; not enforced in
            Phase A.
        max_cost_usd (float | None): Soft upper bound on the cumulative provider cost
            of the chain — surfaced in the UI for future enforcement; not enforced in
            Phase A.
    """

    min_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Escalate when the result's score is strictly below this threshold.",
    )
    max_duration_ms: int | None = Field(
        default=None,
        ge=0,
        description="Soft wall-clock budget per attempt (ms). Surfaced in UI; not enforced in Phase A.",
    )
    max_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        description="Soft cumulative cost budget (USD). Surfaced in UI; not enforced in Phase A.",
    )


class ChainGate:
    """
    Pure policy object that converts a (result, attempt) pair into an escalation decision.

    Wraps a ``ChainGateConfig`` so it can be swapped per stage without changing the
    ``Chain`` class.  Callers should not mutate the config after construction — the
    instance is treated as immutable.
    """

    def __init__(self, cfg: ChainGateConfig) -> None:
        """
        Initialise the gate with a typed config.

        Args:
            cfg (ChainGateConfig): Escalation thresholds — see the class docstring.
        """
        self._cfg = cfg

    @property
    def config(self) -> ChainGateConfig:
        """Read-only access to the underlying config (useful for logging)."""
        return self._cfg

    def should_escalate(self, result: Any, attempt: "ChainAttempt") -> bool:
        """
        Decide whether the chain should try the next provider after this attempt.

        Args:
            result (Any): The provider's raw result (may implement ``ScoredResult``).
            attempt (ChainAttempt): The attempt record built by the chain (provider id,
                duration, error, …).  ``result`` is None when the attempt raised.

        Returns:
            bool: True when the chain should escalate to the next provider.
        """
        # 1. A raised attempt always escalates — the chain cannot use the result.
        if not attempt.succeeded:
            return True

        # 2. Honour the result's own score when it advertises one.
        score = self._extract_score(result)
        if score is not None and score < self._cfg.min_score:
            return True

        # 3. Future extension points (max_duration_ms / max_cost_usd) are parsed but
        # not enforced in Phase A — keep the gate explicit so the UI shows the knobs.
        return False

    @staticmethod
    def _extract_score(result: Any) -> float | None:
        """
        Pull the score off a result if it implements ``ScoredResult``.

        Args:
            result (Any): A provider result instance (may or may not be scored).

        Returns:
            float | None: The advertised score, or None when the result type does not
                participate in scoring.
        """
        if isinstance(result, ScoredResult):
            try:
                return result.score()
            except Exception:  # noqa: BLE001 — defensive; a buggy score() must not break the chain
                return None
        return None

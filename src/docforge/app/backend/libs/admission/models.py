# ====== Code Summary ======
# Value objects for the resource-admission gate (Brique D): the live load snapshot the gate
# reasons over, the resolved set of limits (global + per-collection), and the decision it returns.
# These are plain dataclasses so the decision logic in ResourceAdmitter.evaluate stays pure and
# trivially unit-testable with hand-built inputs (no DB / Redis needed).

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ResourceLimits:
    """
    Resolved admission limits for a single ingest decision.

    Global limits come from RUNTIME_CONFIG (0 = unlimited sentinel); per-collection limits come
    from the collection row (None = no per-collection cap, fall back to global / unlimited).

    Attributes:
        max_queue_depth (int): Reject when the arq backlog (ZCARD) reaches this (0 = unlimited).
        max_in_flight_global (int): Reject when running jobs reach this (0 = unlimited).
        max_in_flight_collection (int | None): Per-collection running+pending cap (None = none).
    """

    max_queue_depth: int
    max_in_flight_global: int
    max_in_flight_collection: int | None = None


@dataclass(slots=True)
class AdmissionSnapshot:
    """
    Live load numbers gathered just before an ingest decision.

    Attributes:
        queue_depth (int): Pending jobs in the arq queue (Redis ZCARD).
        running_global (int): Jobs in status ``running`` across all collections (Postgres).
        inflight_collection (int): running + pending jobs scoped to the target collection.
    """

    queue_depth: int
    running_global: int
    inflight_collection: int


@dataclass(slots=True)
class AdmissionDecision:
    """
    Outcome of the resource-admission gate.

    When ``admitted`` is True the request proceeds to enqueue; ``status_code`` / ``detail`` are
    meaningful only on rejection (mapped straight onto the HTTPException the router raises).

    Attributes:
        admitted (bool): Whether the system can accept this ingest right now.
        reason (str): Short human-readable explanation (logged + echoed on rejection).
        status_code (int): HTTP status to raise on rejection (429 capacity).
        detail (dict): Structured rejection body (limit + current value).
    """

    admitted: bool
    reason: str
    status_code: int = 0
    detail: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def admit(cls, reason: str) -> "AdmissionDecision":
        """Build an accepting decision (status/detail unused)."""
        return cls(admitted=True, reason=reason)

    @classmethod
    def reject(cls, *, status_code: int, reason: str, detail: dict[str, Any]) -> "AdmissionDecision":
        """Build a rejecting decision carrying the HTTP status and structured body."""
        return cls(admitted=False, reason=reason, status_code=status_code, detail=detail)


# ------------------- Public API ------------------- #
__all__ = ["ResourceLimits", "AdmissionSnapshot", "AdmissionDecision"]

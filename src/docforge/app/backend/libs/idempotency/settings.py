# ====== Code Summary ======
# IdempotencySettings — the frozen, injected configuration of the idempotency middleware. The
# composition root (``backend/app.py``) builds it ONCE from the runtime config and hands it to
# ``IdempotencyMiddleware``; nothing inside this package reads the global config.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IdempotencySettings:
    """
    Immutable idempotency knobs, mirroring the ``IDEMPOTENCY_*`` runtime settings.

    Attributes:
        enabled (bool): Master switch; False makes the middleware a transparent passthrough.
        ttl_hours (int): How long a cached record is honoured (stamped as ``expires_at`` at insert).
        inprogress_ttl_seconds (int): Age past which an in-progress guard is reclaimable by a retry.
        max_body_bytes (int): Symmetric cap on the request body buffered to fingerprint it AND on the
            response body cached for replay.
    """

    enabled: bool
    ttl_hours: int
    inprogress_ttl_seconds: int
    max_body_bytes: int


__all__ = ["IdempotencySettings"]

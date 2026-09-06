# ====== Code Summary ======
# RateLimitEngine — the reusable moving-window request limiter shared by the API gates. It owns one
# in-process window store and exposes the two operations a caller needs: consume one hit for a bucket
# key (fail-open on a storage error), and emit the 429 + Retry-After response for an over-budget key.
# The per-minute budget is read from RUNTIME_CONFIG on every call, so a runbook toggle needs no code
# change. Two callers use it: RateLimitMiddleware (the post-auth per-key / per-IP budget) and the
# AuthMiddleware failure path (the pre-route per-IP budget that throttles credential-flood 401s).

# ====== Standard Library Imports ======
import math
import time

# ====== Third-Party Library Imports ======
from fastapi.responses import JSONResponse
from limits import RateLimitItemPerMinute
from limits.aio.storage import MemoryStorage
from limits.aio.strategies import MovingWindowRateLimiter
from loggerplusplus import LoggerClass
from starlette.types import Receive, Scope, Send

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG

# ====== Local Project Imports ======
from ..logsafe import LogSafeHelpers


class RateLimitEngine(LoggerClass):
    """Reusable per-caller moving-window limiter: consume a hit, or emit the 429 for an over-budget key."""

    def __init__(self) -> None:
        """Build the limiter over an in-process moving-window store (one window state per instance)."""
        # 1. Init the logger, then hold the moving-window limiter over an in-process store. The store
        #    is per-instance — the two API gates keep independent windows (their key namespaces never
        #    overlap), so nothing needs to be shared between them.
        LoggerClass.__init__(self)
        self._limiter = MovingWindowRateLimiter(MemoryStorage())

    def __item(self) -> RateLimitItemPerMinute:
        """
        Build the per-minute limit item from the current runtime budget.

        Returns:
            RateLimitItemPerMinute: The rolling per-minute budget read from RUNTIME_CONFIG.
        """
        # 1. Read the budget per call so a runbook change to RATE_LIMIT_PER_MINUTE applies live.
        return RateLimitItemPerMinute(RUNTIME_CONFIG.RATE_LIMIT_PER_MINUTE)

    async def allow(self, key: str) -> bool:
        """
        Consume one hit from a bucket key's rolling per-minute window.

        Args:
            key (str): The caller's bucket key.

        Returns:
            bool: True when the request is within budget (or the limiter is unavailable — FAIL OPEN),
            False when the caller is over budget.
        """
        # 1. Consume a hit. FAIL OPEN: a storage error (e.g. a Redis outage once the store is
        #    externalised) must never take down legit traffic — the limiter is an abuse mitigation,
        #    not a correctness gate, so on its own failure we log and allow rather than 500.
        try:
            return await self._limiter.hit(self.__item(), key)
        except Exception:
            # An IP bucket key can embed a client-controlled X-Forwarded-For value — sanitise it so a
            # crafted header cannot forge log records, and never treat it as a trusted identifier.
            self.logger.warning(
                f"Rate limiter unavailable; failing open for this request "
                f"(key={LogSafeHelpers.sanitize(key)})"
            )
            return True

    async def reject(self, scope: Scope, receive: Receive, send: Send, key: str) -> None:
        """
        Emit a 429 carrying a Retry-After derived from the rolling-window reset instant.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The ASGI receive channel.
            send (Send): The ASGI send channel.
            key (str): The caller's bucket key (source of the window stats).
        """
        # 1. The window reset instant tells the caller how long to back off (>= 1s). If the stats read
        #    itself errors, fall back to a whole-minute back-off rather than 500 (still a valid 429).
        try:
            reset_time, _ = await self._limiter.get_window_stats(self.__item(), key)
            retry_after = max(1, math.ceil(reset_time - time.time()))
        except Exception:
            # Sanitise the (possibly XFF-derived, client-controlled) key before logging it.
            self.logger.warning(
                f"Rate limiter window-stats unavailable; using default Retry-After "
                f"(key={LogSafeHelpers.sanitize(key)})"
            )
            retry_after = 60

        # 2. A JSON 429 mirroring the shape the auth middleware returns (a `detail` body).
        response = JSONResponse(
            {"detail": "Rate limit exceeded. Please retry later."},
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )
        await response(scope, receive, send)


__all__ = ["RateLimitEngine"]

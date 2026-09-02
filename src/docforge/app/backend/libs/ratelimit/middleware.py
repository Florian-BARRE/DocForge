# ====== Code Summary ======
# RateLimitMiddleware — a pure ASGI middleware enforcing a per-caller request budget on /api/v1/*.
# It is wired INNER to AuthMiddleware, so the principal the authN gate injected into scope["state"]
# is available here for per-tenant keying; with auth off it keys by client IP. Enable + limit are read
# from RUNTIME_CONFIG on every request (OFF by default → fully transparent passthrough), so a runbook
# toggle needs no code change. Over-budget requests are rejected with 429 + a Retry-After derived from
# the rolling-window reset. The moving-window counter is in-process (per app worker) — adequate for the
# single-process app; point the `limits` storage at Redis to share one budget across replicas.

# ====== Standard Library Imports ======
import math
import time

# ====== Third-Party Library Imports ======
from fastapi.responses import JSONResponse
from limits import RateLimitItemPerMinute
from limits.aio.storage import MemoryStorage
from limits.aio.strategies import MovingWindowRateLimiter
from loggerplusplus import loggerplusplus
from starlette.types import ASGIApp, Receive, Scope, Send

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG

# ====== Local Project Imports ======
from .exemptions import RateLimitExemptions
from .keying import RateLimitKeyResolver

logger = loggerplusplus.bind(identifier="RateLimit")


class RateLimitMiddleware:
    """Pure ASGI middleware applying a per-caller per-minute request budget to the API surface."""

    def __init__(self, app: ASGIApp) -> None:
        """
        Wrap the downstream ASGI application and build the in-process rate-limiter.

        Args:
            app (ASGIApp): The next ASGI application in the stack.
        """
        # 1. Hold the wrapped app; the limiter's window state lives in an in-process store.
        self.app = app
        self._limiter = MovingWindowRateLimiter(MemoryStorage())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Enforce the per-caller budget (when enabled + applicable) before delegating downstream.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The ASGI receive channel.
            send (Send): The ASGI send channel.
        """
        # 1. Non-HTTP scopes and a disabled limiter → transparent passthrough (the default state).
        if scope["type"] != "http" or not RUNTIME_CONFIG.RATE_LIMIT_ENABLED:
            await self.app(scope, receive, send)
            return

        # 2. Only /api/v1/* minus the high-frequency job-monitoring subtree is limited.
        if not RateLimitExemptions.is_limited(scope["path"]):
            await self.app(scope, receive, send)
            return

        # 3. Derive the bucket key from the auth identity (injected by AuthMiddleware) or client IP.
        principal = scope.get("state", {}).get("principal")
        key = RateLimitKeyResolver.resolve(
            scope, principal, RUNTIME_CONFIG.RATE_LIMIT_TRUST_FORWARDED_FOR
        )

        # 4. Consume one hit from the caller's rolling per-minute window. FAIL OPEN: a storage error
        #    (e.g. a Redis outage once the store is externalised) must never take down legit traffic —
        #    the limiter is an abuse mitigation, not a correctness gate, so on its own failure we log
        #    and allow rather than 500 every request (a self-DoS).
        item = RateLimitItemPerMinute(RUNTIME_CONFIG.RATE_LIMIT_PER_MINUTE)
        try:
            allowed = await self._limiter.hit(item, key)
        except Exception:
            logger.warning(f"Rate limiter unavailable; failing open for this request (key={key})")
            allowed = True
        if allowed:
            await self.app(scope, receive, send)
            return

        # 5. Over budget → 429 with a Retry-After (whole seconds until the window frees a slot).
        await self._reject(scope, receive, send, item, key)

    async def _reject(
        self, scope: Scope, receive: Receive, send: Send, item: RateLimitItemPerMinute, key: str
    ) -> None:
        """
        Send a 429 response carrying a Retry-After derived from the rolling-window reset instant.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The ASGI receive channel.
            send (Send): The ASGI send channel.
            item (RateLimitItemPerMinute): The limit that was breached (source of the window stats).
            key (str): The caller's bucket key.
        """
        # 1. The window reset instant tells the caller how long to back off (>= 1s). If the stats read
        #    itself errors, fall back to a whole-minute back-off rather than 500 (still a valid 429).
        try:
            reset_time, _ = await self._limiter.get_window_stats(item, key)
            retry_after = max(1, math.ceil(reset_time - time.time()))
        except Exception:
            logger.warning(
                f"Rate limiter window-stats unavailable; using default Retry-After (key={key})"
            )
            retry_after = 60

        # 2. A JSON 429 mirroring the shape the auth middleware returns (a `detail` body).
        response = JSONResponse(
            {"detail": "Rate limit exceeded. Please retry later."},
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )
        await response(scope, receive, send)


__all__ = ["RateLimitMiddleware"]

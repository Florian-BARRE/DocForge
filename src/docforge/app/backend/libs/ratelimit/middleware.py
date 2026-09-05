# ====== Code Summary ======
# RateLimitMiddleware — a pure ASGI middleware enforcing a per-caller request budget on /api/v1/*.
# It is wired INNER to AuthMiddleware, so the principal the authN gate injected into scope["state"]
# is available here for per-tenant keying; with auth off it keys by client IP. Enable + limit are read
# from RUNTIME_CONFIG on every request (OFF by default → fully transparent passthrough), so a runbook
# toggle needs no code change. Over-budget requests are rejected with 429 + a Retry-After derived from
# the rolling-window reset. The moving-window counter is in-process (per app worker) — adequate for the
# single-process app; point the `limits` storage at Redis to share one budget across replicas.

# ====== Third-Party Library Imports ======
from starlette.types import ASGIApp, Receive, Scope, Send

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG

# ====== Local Project Imports ======
from .engine import RateLimitEngine
from .exemptions import RateLimitExemptions
from .keying import RateLimitKeyResolver


class RateLimitMiddleware:
    """Pure ASGI middleware applying a per-caller per-minute request budget to the API surface."""

    def __init__(self, app: ASGIApp) -> None:
        """
        Wrap the downstream ASGI application and build the in-process rate-limiter.

        Args:
            app (ASGIApp): The next ASGI application in the stack.
        """
        # 1. Hold the wrapped app; the shared engine owns the in-process window store.
        self.app = app
        self._engine = RateLimitEngine()

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

        # 4. Consume one hit from the caller's rolling per-minute window (fail-open on a store error).
        if await self._engine.allow(key):
            await self.app(scope, receive, send)
            return

        # 5. Over budget → 429 with a Retry-After (whole seconds until the window frees a slot).
        await self._engine.reject(scope, receive, send, key)


__all__ = ["RateLimitMiddleware"]

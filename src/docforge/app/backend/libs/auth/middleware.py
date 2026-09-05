# ====== Code Summary ======
# The authN gate as a PURE ASGI middleware — it runs BEFORE FastAPI reads/validates the request body,
# so a missing/revoked bearer is rejected with 401 even on a malformed-body request (no more 422-before-
# 401 ordering). On success it injects the resolved principal into `scope["state"]` so the per-endpoint
# authZ dependency (`require`) can read it WITHOUT re-authenticating. Only `/api/v1/*` is gated; scalar,
# `/openapi.json` and docs live outside that prefix and pass through untouched. With AUTH_ENABLED=false
# `authenticate` returns the synthetic root, so this middleware stays fully transparent.
#
# Because the rate limiter proper sits INNER to this gate, a request that fails auth short-circuits here
# and never reaches it — so this gate ALSO throttles failed-auth traffic by client IP (when the limiter
# is enabled) to close the credential-flood / 401-DoS bypass.

# ====== Third-Party Library Imports ======
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG

# ====== Local Project Imports ======
from ..ratelimit import RateLimitEngine, RateLimitKeyResolver
from .dependency import authenticate

# Only requests under this prefix are authenticated; everything else (scalar/openapi/docs) is public.
_API_PREFIX = "/api/v1"


class AuthMiddleware:
    """
    Pure ASGI middleware that authenticates every ``/api/v1`` request before body parsing.

    Running at the ASGI layer (rather than as a FastAPI dependency) guarantees the authN check
    fires before FastAPI reads and validates the request body — so a bad credential yields 401,
    never a 422 raised while parsing a malformed body first. The resolved principal is stashed in
    ``scope["state"]`` for the downstream authZ dependency to consume.
    """

    def __init__(self, app: ASGIApp) -> None:
        """
        Wrap the downstream ASGI application.

        Args:
            app (ASGIApp): The next ASGI application in the stack.
        """
        # 1. Hold the wrapped app; the failure-path throttle keeps its own in-process window store.
        #    The rate limiter proper (RateLimitMiddleware) sits INNER to this gate, so it never sees a
        #    request that fails auth — a credential-flood 401 would bypass it entirely. This engine
        #    closes that hole by throttling failed-auth traffic here, keyed by client IP.
        self.app = app
        self._failure_throttle = RateLimitEngine()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Authenticate the request (when applicable) before delegating to the wrapped app.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The ASGI receive channel.
            send (Send): The ASGI send channel.
        """
        # 1. Only HTTP requests are authenticated — pass every other scope type through untouched.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 2. Public surfaces live outside /api/v1 (scalar/openapi/docs) — no authN, pass through.
        if not scope["path"].startswith(_API_PREFIX):
            await self.app(scope, receive, send)
            return

        # 3. Resolve the principal BEFORE the body is ever read; a 401 short-circuits the request.
        request = Request(scope, receive)
        try:
            principal = await authenticate(request)
        except HTTPException as exc:
            await self.__reject_auth_failure(scope, receive, send, exc)
            return

        # 4. Inject the principal so the authZ dependency reads it without re-authenticating.
        #    Starlette's `Request.state` is backed by `scope["state"]`, so the endpoint sees it.
        scope.setdefault("state", {})["principal"] = principal

        # 5. Authenticated — hand off to the wrapped application.
        await self.app(scope, receive, send)

    async def __reject_auth_failure(
        self, scope: Scope, receive: Receive, send: Send, exc: HTTPException
    ) -> None:
        """
        Emit the auth-failure response — a 429 when the credential-flood budget is exhausted, else the 401.

        The rate limiter proper runs INNER to this gate and so never sees a request that fails auth;
        this throttles that traffic by client IP to close the credential-flood / 401-DoS bypass. The
        job-poll/SSE exemption is deliberately NOT applied here: a failed-auth request is never a
        legitimate high-frequency poll (those are authenticated and throttled per-key downstream), so
        exempting any /api/v1 subtree on this path would simply reopen the bypass on that subtree.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The ASGI receive channel.
            send (Send): The ASGI send channel.
            exc (HTTPException): The authN failure to relay when the caller is within budget.
        """
        # 1. Limiter off → transparent: relay the original credential-failure response unchanged.
        if RUNTIME_CONFIG.RATE_LIMIT_ENABLED:
            # 2. Count this failed attempt against the caller's IP window; over budget → 429 instead
            #    of yet another 401, so a bad-credential flood is throttled like any other abuse.
            ip = RateLimitKeyResolver.client_ip(
                scope, RUNTIME_CONFIG.RATE_LIMIT_TRUST_FORWARDED_FOR
            )
            key = f"authfail:{ip}"
            if not await self._failure_throttle.allow(key):
                await self._failure_throttle.reject(scope, receive, send, key)
                return

        # 3. Within budget (or limiter off) → relay the authN failure verbatim (opaque 401 + headers).
        response = JSONResponse(
            {"detail": exc.detail},
            status_code=exc.status_code,
            headers=exc.headers,
        )
        await response(scope, receive, send)


__all__ = ["AuthMiddleware"]

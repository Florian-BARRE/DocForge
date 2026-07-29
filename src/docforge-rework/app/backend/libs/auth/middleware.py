# ====== Code Summary ======
# The authN gate as a PURE ASGI middleware — it runs BEFORE FastAPI reads/validates the request body,
# so a missing/revoked bearer is rejected with 401 even on a malformed-body request (no more 422-before-
# 401 ordering). On success it injects the resolved principal into `scope["state"]` so the per-endpoint
# authZ dependency (`require`) can read it WITHOUT re-authenticating. Only `/api/v1/*` is gated; scalar,
# `/openapi.json` and docs live outside that prefix and pass through untouched. With AUTH_ENABLED=false
# `authenticate` returns the synthetic root, so this middleware stays fully transparent.

# ====== Third-Party Library Imports ======
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# ====== Local Project Imports ======
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
        # 1. Hold the wrapped app; the middleware carries no other state.
        self.app = app

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
            response = JSONResponse(
                {"detail": exc.detail},
                status_code=exc.status_code,
                headers=exc.headers,
            )
            await response(scope, receive, send)
            return

        # 4. Inject the principal so the authZ dependency reads it without re-authenticating.
        #    Starlette's `Request.state` is backed by `scope["state"]`, so the endpoint sees it.
        scope.setdefault("state", {})["principal"] = principal

        # 5. Authenticated — hand off to the wrapped application.
        await self.app(scope, receive, send)


__all__ = ["AuthMiddleware"]

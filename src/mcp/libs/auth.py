# ====== Code Summary ======
# BearerPassthroughMiddleware — a raw ASGI middleware wrapping the streamable-HTTP MCP app. It
# captures each request's incoming "Authorization: Bearer <docforge-api-key>" header into a
# contextvar (token_context.py) so downstream tool calls forward the CALLER's own DocForge API key
# upstream — the MCP does not gate access itself. Auth is fully delegated to DocForge: a
# missing/invalid/unscoped key surfaces as a 401/403 from the DocForge API, relayed to the caller.
#
# Implemented as a plain ASGI callable, NOT starlette's BaseHTTPMiddleware, because
# BaseHTTPMiddleware runs the downstream app inside a separate anyio task via call_next() — a
# contextvar set in dispatch() is not guaranteed to be visible there. A raw ASGI wrapper calls the
# app inline in the same task, so the token set here stays visible through every nested tool call.

from __future__ import annotations

# ====== Third-Party Library Imports ======
from starlette.types import ASGIApp, Receive, Scope, Send

# ====== Local Project Imports ======
from .token_context import incoming_docforge_token


class BearerPassthroughMiddleware:
    """
    Stash the incoming request's bearer token into a contextvar for the duration of the call.

    Carries no secret of its own — it neither validates nor rejects a request; DocForge's own API
    enforces auth (and scope) on every proxied call the tools go on to make.
    """

    def __init__(self, app: ASGIApp) -> None:
        """
        Wrap the downstream ASGI application.

        Args:
            app (ASGIApp): The wrapped ASGI application (the MCP streamable-HTTP app).
        """
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Set the token contextvar for HTTP requests, then delegate to the wrapped app.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The ASGI receive channel.
            send (Send): The ASGI send channel.
        """
        # 1. Only HTTP connections carry an Authorization header worth extracting.
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        # 2. Stash the caller's token (or None) for the lifetime of this request only.
        token = self._extract_bearer(scope)
        reset = incoming_docforge_token.set(token)
        try:
            await self._app(scope, receive, send)
        finally:
            incoming_docforge_token.reset(reset)

    @staticmethod
    def _extract_bearer(scope: Scope) -> str | None:
        """
        Pull the bearer token out of the raw ASGI header list.

        Args:
            scope (Scope): The ASGI connection scope.

        Returns:
            str | None: The token, or None when the header is absent or not a bearer token.
        """
        # 1. ASGI headers are a list of (lowercase-name, value) byte-string pairs.
        raw_headers = dict(scope.get("headers") or [])
        raw_value = raw_headers.get(b"authorization")
        if not raw_value:
            return None

        # 2. Only the bearer scheme carries a DocForge API key; anything else is ignored.
        value = raw_value.decode("latin-1")
        prefix = "Bearer "
        if not value.startswith(prefix):
            return None
        return value[len(prefix) :] or None


__all__ = ["BearerPassthroughMiddleware"]

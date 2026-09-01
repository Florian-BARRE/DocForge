# ====== Code Summary ======
# BearerPassthroughMiddleware — a raw ASGI middleware wrapping the streamable-HTTP MCP app. It
# captures each request's incoming "Authorization: Bearer <docforge-api-key>" header into a
# contextvar (token_context.py) so downstream tool calls forward the CALLER's own DocForge API key
# upstream — the MCP does not gate access itself beyond requiring that a bearer be present.
#
# THIS is the enforcement point that closes the anonymous-access hole: a request with NO bearer (or
# a non-bearer / empty one) is rejected here with 401 and the wrapped app is never invoked — it
# must NOT fall through to any fallback token. Once a request DOES carry a bearer, validating it
# (and its scope) is fully delegated to DocForge: an invalid/unscoped key surfaces as a 401/403
# from the DocForge API, relayed to the caller through the tool call.
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

# Minimal JSON body for the 401 — kept ASCII, no dependency on a JSON encoder for one static object.
_UNAUTHORIZED_BODY = b'{"error": "Authorization required"}'


class BearerPassthroughMiddleware:
    """
    Require a caller bearer token on every HTTP request, then forward it via a contextvar.

    A request with no ``Authorization: Bearer <token>`` header is refused with 401 before the
    wrapped app runs at all — this transport never falls back to a shared/local credential over the
    network. A request that DOES carry a bearer is not validated here: the token is stashed for the
    duration of the call and DocForge's own API enforces auth (and scope) on every proxied call the
    tools go on to make.
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
        Gate HTTP requests on a bearer token, then delegate to the wrapped app.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The ASGI receive channel.
            send (Send): The ASGI send channel.
        """
        # 1. Only HTTP connections carry an Authorization header worth extracting.
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        # 2. No (or malformed/empty) bearer -> reject here; the wrapped app never runs, so no tool
        #    call can ever resolve the fallback DOCFORGE_API_TOKEN client on this transport.
        token = self._extract_bearer(scope)
        if not token:
            await self._reject_unauthorized(send)
            return

        # 3. Stash the caller's token for the lifetime of this request only.
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

        # 2. Only the bearer scheme carries a DocForge API key; anything else is ignored. The scheme
        #    name is case-insensitive per RFC 7235, so a client sending "bearer <tok>" is accepted.
        value = raw_value.decode("latin-1")
        scheme, _, credentials = value.partition(" ")
        if scheme.lower() != "bearer":
            return None
        return credentials.strip() or None

    @staticmethod
    async def _reject_unauthorized(send: Send) -> None:
        """
        Send a plain 401 JSON response directly at the ASGI layer, bypassing the wrapped app.

        Args:
            send (Send): The ASGI send channel.
        """
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_UNAUTHORIZED_BODY)).encode("ascii")),
                    # Spec-compliant 401 advertises the scheme the client must use.
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _UNAUTHORIZED_BODY})


__all__ = ["BearerPassthroughMiddleware"]

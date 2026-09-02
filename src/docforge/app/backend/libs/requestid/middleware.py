# ====== Code Summary ======
# RequestIdMiddleware — a pure ASGI middleware that gives every request a correlation id and threads
# it through the whole response path. It honours an inbound `X-Request-ID` / `X-Correlation-ID` (so an
# upstream proxy's id is preserved end-to-end), else mints one; binds it into the shared correlation
# ContextVar so every log line emitted during the request carries it; and echoes it back as
# `X-Request-ID` on the response. It is wired OUTER to AuthMiddleware and RateLimitMiddleware so even
# their short-circuit 401/429 responses are emitted inside the correlation context AND carry the
# header. Always-on and zero-config: a correlation id is not PII and adds no failure mode.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# ====== Internal Project Imports ======
from shared_libs.observability import CorrelationContext

# ====== Local Project Imports ======
from .helpers import RequestIdHelpers

# The response header the correlation id is echoed back on (also the primary inbound header honoured).
_RESPONSE_HEADER = b"x-request-id"


class RequestIdMiddleware:
    """Pure ASGI middleware that binds a per-request correlation id and echoes it on the response."""

    def __init__(self, app: ASGIApp) -> None:
        """
        Wrap the downstream ASGI application.

        Args:
            app (ASGIApp): The next ASGI application in the stack.
        """
        # 1. Hold the wrapped app; the id itself lives per-request in the shared ContextVar.
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Resolve + bind the correlation id, then delegate — stamping the id onto the response.

        Args:
            scope (Scope): The ASGI connection scope.
            receive (Receive): The ASGI receive channel.
            send (Send): The ASGI send channel.
        """
        # 1. Only HTTP requests carry a correlation id — pass every other scope type through untouched.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 2. Honour an upstream id when present + valid, else mint one; bind it for this request.
        correlation_id = RequestIdHelpers.resolve(scope.get("headers", []))
        token = CorrelationContext.set(correlation_id)

        # 3. Wrap `send` so the id is injected into the response start (works for downstream 401/429).
        stamped_send = self._make_stamped_send(send, correlation_id)

        # 4. Delegate — always release the context binding, even on a downstream error.
        try:
            await self.app(scope, receive, stamped_send)
        finally:
            CorrelationContext.reset(token)

    def _make_stamped_send(self, send: Send, correlation_id: str) -> Send:
        """
        Build a `send` wrapper that injects the correlation id header into the response start.

        Args:
            send (Send): The original ASGI send channel.
            correlation_id (str): The id to echo back on the response.

        Returns:
            Send: A send callable that stamps `X-Request-ID` onto the `http.response.start` message.
        """
        header_value = correlation_id.encode("latin-1")

        async def stamped_send(message: Message) -> None:
            # 1. Only the response-start message carries headers; everything else passes straight through.
            if message["type"] == "http.response.start":
                self._inject_header(message, header_value)
            await send(message)

        return stamped_send

    @staticmethod
    def _inject_header(message: dict[str, Any], header_value: bytes) -> None:
        """
        Set (replacing any existing) the correlation id header on a response-start message.

        Args:
            message (dict): The `http.response.start` ASGI message.
            header_value (bytes): The correlation id, already encoded.
        """
        # 1. Drop any pre-existing X-Request-ID (a downstream response must not shadow our id), then set ours.
        headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != _RESPONSE_HEADER]
        headers.append((_RESPONSE_HEADER, header_value))
        message["headers"] = headers


__all__ = ["RequestIdMiddleware"]

# ====== Code Summary ======
# IdempotencyResponseBuffer — captures the downstream handler's ASGI response (the http.response.start
# status + headers and every http.response.body chunk) INSTEAD of sending it, so the idempotency
# middleware can inspect the final status (cache a definitive < 500, drop a 5xx) and store the body
# bytes for later replay. Once the middleware has decided, it calls ``flush`` to emit the captured
# messages to the real ``send`` verbatim — a buffered (never-replayed) request therefore streams the
# handler's exact bytes, headers and status through, just deferred until the caching decision is made.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from starlette.types import Message, Send


class IdempotencyResponseBuffer:
    """Buffers a handler's ASGI response so the middleware can inspect + cache it before flushing."""

    def __init__(self) -> None:
        """Initialise an empty buffer (no response captured yet)."""
        # 1. The captured start message (status + headers) and the ordered body chunks.
        self._start: Message | None = None
        self._body_chunks: list[bytes] = []

    async def send(self, message: Message) -> None:
        """
        Capture one outgoing ASGI response message instead of sending it downstream.

        Args:
            message (Message): An ASGI response message (``http.response.start`` or ``.body``).
        """
        # 1. Remember the start line (status + headers) and accumulate body bytes in order.
        if message["type"] == "http.response.start":
            self._start = message
        elif message["type"] == "http.response.body":
            self._body_chunks.append(message.get("body", b""))

    @property
    def status(self) -> int | None:
        """int | None: The captured response status, or None when nothing was sent."""
        return None if self._start is None else self._start["status"]

    @property
    def body(self) -> bytes:
        """bytes: The full captured response body (all chunks concatenated in order)."""
        return b"".join(self._body_chunks)

    @property
    def media_type(self) -> str | None:
        """
        str | None: The captured response ``content-type`` header value, if present.

        Returns:
            str | None: The decoded content-type, or None when the handler set none.
        """
        # 1. ASGI headers are a list of lower-cased (name, value) byte tuples; find content-type.
        if self._start is None:
            return None
        for name, value in self._start.get("headers", []):
            if name == b"content-type":
                return value.decode("latin-1")
        return None

    async def flush(self, send: Send) -> None:
        """
        Emit the buffered response to the real ``send`` verbatim (status, headers, then body).

        Args:
            send (Send): The request's real ASGI send channel.
        """
        # 1. Nothing captured (a handler that sent no response) → nothing to flush.
        if self._start is None:
            return
        # 2. Replay the start line, then the body as a single final chunk (byte-identical payload).
        await send(self._start)
        await send({"type": "http.response.body", "body": self.body, "more_body": False})


__all__ = ["IdempotencyResponseBuffer"]

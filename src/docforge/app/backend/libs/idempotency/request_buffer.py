# ====== Code Summary ======
# IdempotencyRequestBuffer — the ASGI body-plumbing for the idempotency middleware. To fingerprint a
# request the middleware must read its body from the ``receive`` channel, but the downstream handler
# still needs to read that same body — so this buffer drains ``receive`` (up to a hard cap), remembers
# every message, and hands back a REPLAY receive that re-feeds the buffered messages before delegating
# to the original channel. It also computes the sha256 fingerprint of the body. If the body exceeds
# the cap it stops buffering (``over_cap``): the middleware then skips idempotency and uses the replay
# receive purely to stream the already-read + remaining bytes through untouched (never OOM).

# ====== Standard Library Imports ======
from __future__ import annotations

import hashlib

# ====== Third-Party Library Imports ======
from starlette.types import Message, Receive


class IdempotencyRequestBuffer:
    """Drains + remembers a request body so it can be fingerprinted AND replayed to the handler."""

    def __init__(self, messages: list[Message], body: bytes | None) -> None:
        """
        Args:
            messages (list[Message]): The ASGI messages read off ``receive`` (replayed downstream).
            body (bytes | None): The full body bytes when captured within the cap, else None (the
                over-cap signal — the body was too large to buffer/fingerprint safely).
        """
        # 1. Hold the captured messages + body; ``body is None`` means the cap was exceeded.
        self._messages = messages
        self._body = body

    @property
    def over_cap(self) -> bool:
        """bool: True when the body exceeded the buffer cap (idempotency must be skipped)."""
        return self._body is None

    @property
    def fingerprint(self) -> str:
        """
        str: The sha256 hex of the buffered body.

        Raises:
            ValueError: When called on an over-cap buffer (no body was captured to fingerprint).
        """
        # 1. Guard: an over-cap buffer has no body to hash — the middleware must not reach here.
        if self._body is None:
            raise ValueError("Cannot fingerprint an over-cap request body.")
        return hashlib.sha256(self._body).hexdigest()

    @classmethod
    async def read(cls, receive: Receive, max_bytes: int) -> IdempotencyRequestBuffer:
        """
        Drain the request body off ``receive`` up to ``max_bytes``, remembering every message.

        Args:
            receive (Receive): The ASGI receive channel to drain.
            max_bytes (int): The hard cap — once the accumulated body exceeds it, buffering stops and
                the result is flagged ``over_cap`` (body left as None).

        Returns:
            IdempotencyRequestBuffer: The captured messages + body (or the over-cap signal).
        """
        # 1. Read messages until the body is complete (no more_body), the client disconnects, or the
        #    accumulated size passes the cap. Every message is remembered for verbatim replay.
        messages: list[Message] = []
        chunks: list[bytes] = []
        total = 0
        over_cap = False
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] != "http.request":
                # A disconnect (or any non-body message) ends the read — there is no body to add.
                break
            chunks.append(message.get("body", b""))
            total += len(message.get("body", b""))
            if total > max_bytes:
                over_cap = True
                break
            if not message.get("more_body", False):
                break

        # 2. On an over-cap read, drop the accumulated bytes (never keep an unbounded body in memory).
        body = None if over_cap else b"".join(chunks)
        return cls(messages, body)

    def replay_receive(self, original: Receive) -> Receive:
        """
        Build a receive channel that re-feeds the buffered messages, then delegates to the original.

        Args:
            original (Receive): The request's real receive channel (for any bytes read past the cap).

        Returns:
            Receive: A receive callable yielding the buffered messages first, then the live channel.
        """
        # 1. A cursor over the remembered messages; once exhausted, fall through to the real channel
        #    (only relevant on an over-cap read, where the body was not fully drained here).
        pending = iter(self._messages)

        async def _receive() -> Message:
            # 2. Serve a buffered message if one remains, else defer to the original channel.
            try:
                return next(pending)
            except StopIteration:
                return await original()

        return _receive


__all__ = ["IdempotencyRequestBuffer"]

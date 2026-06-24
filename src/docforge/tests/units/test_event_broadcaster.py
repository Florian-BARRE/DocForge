# ====== Code Summary ======
# Unit tests for EventBroadcaster fan-out logic — subscribe/unsubscribe registration, delivery to
# every client queue, drop-oldest back-pressure when a queue is full, and malformed-payload decode.
# The Redis-backed start()/stop() lifecycle is not exercised here (no broker in unit tests); only the
# in-memory fan-out is, via the name-mangled private helpers.

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from libs.observability.events import EventBroadcaster


def _make(maxsize: int = 2) -> EventBroadcaster:
    """Build a broadcaster without opening any Redis connection."""
    return EventBroadcaster("redis://localhost:6379", queue_maxsize=maxsize)


class TestEventBroadcasterFanOut:
    """In-memory subscribe/fan-out behaviour of EventBroadcaster."""

    def test_subscribe_returns_bounded_queue_and_registers_it(self) -> None:
        """subscribe() hands back a queue sized to queue_maxsize and tracks it internally."""
        broadcaster = _make(maxsize=3)
        queue = broadcaster.subscribe()
        assert queue.maxsize == 3
        assert queue in broadcaster._subscribers

    def test_fan_out_delivers_to_every_subscriber(self) -> None:
        """An event is pushed onto all registered subscriber queues."""
        broadcaster = _make()
        q1 = broadcaster.subscribe()
        q2 = broadcaster.subscribe()

        event = {"type": "job.updated", "job": {"id": "j1"}}
        broadcaster._EventBroadcaster__fan_out(event)  # type: ignore[attr-defined]

        assert q1.get_nowait() == event
        assert q2.get_nowait() == event

    def test_fan_out_drops_oldest_on_overflow(self) -> None:
        """When a queue is full, the oldest event is discarded to make room for the newest."""
        broadcaster = _make(maxsize=2)
        queue = broadcaster.subscribe()

        # Fill beyond capacity: e0 should be evicted, leaving e1, e2 in order.
        for i in range(3):
            broadcaster._EventBroadcaster__fan_out({"n": i})  # type: ignore[attr-defined]

        assert queue.get_nowait() == {"n": 1}
        assert queue.get_nowait() == {"n": 2}
        assert queue.empty()

    def test_unsubscribe_stops_delivery(self) -> None:
        """After unsubscribe(), a queue no longer receives fanned-out events."""
        broadcaster = _make()
        queue = broadcaster.subscribe()
        broadcaster.unsubscribe(queue)

        broadcaster._EventBroadcaster__fan_out({"type": "job.updated"})  # type: ignore[attr-defined]
        assert queue.empty()

    def test_unsubscribe_is_idempotent(self) -> None:
        """Unsubscribing an unknown queue is a harmless no-op."""
        broadcaster = _make()
        broadcaster.unsubscribe(asyncio.Queue())  # not registered — must not raise


class TestEventBroadcasterDecode:
    """Malformed payloads are dropped, valid JSON is decoded to a dict."""

    def test_decode_valid_json_bytes(self) -> None:
        """A UTF-8 JSON byte payload decodes into the event dict."""
        broadcaster = _make()
        decoded = broadcaster._EventBroadcaster__decode(b'{"type": "job.updated"}')  # type: ignore[attr-defined]
        assert decoded == {"type": "job.updated"}

    def test_decode_malformed_returns_none(self) -> None:
        """Invalid JSON returns None instead of raising."""
        broadcaster = _make()
        assert broadcaster._EventBroadcaster__decode(b"not json") is None  # type: ignore[attr-defined]

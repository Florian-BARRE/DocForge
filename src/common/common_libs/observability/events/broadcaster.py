# ====== Code Summary ======
# EventBroadcaster — a single Redis pub/sub subscriber per backend process that fans out every
# monitoring event from the shared `docforge:events` channel to per-client asyncio.Queue consumers.
# One subscription serves N SSE connections (N browser tabs); multiple backend instances each run
# their own broadcaster and all receive every event (pub/sub fan-out). A DEDICATED Redis client is
# used because a connection in subscribe mode cannot issue other commands — the arq pool is reserved
# for queue-introspection commands. Per-client queues are bounded and drop the oldest event under
# back-pressure so one slow browser cannot grow memory unboundedly.

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio
import json
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from redis.asyncio import Redis

# ====== Local Project Imports ======
from .channels import EVENTS_CHANNEL

# Self-healing resubscribe backoff bounds — a dropped Redis connection is retried with capped
# exponential backoff so fan-out resumes without a process restart.
_RESUBSCRIBE_BACKOFF_INITIAL_S: float = 1.0
_RESUBSCRIBE_BACKOFF_MAX_S: float = 30.0


class EventBroadcaster(LoggerClass):
    """
    Fan-out hub for monitoring events: one Redis subscription → many SSE clients.

    A background task subscribes once to ``docforge:events`` and pushes each decoded event onto
    every registered subscriber queue. SSE endpoints call :meth:`subscribe` to obtain their own
    bounded queue, stream from it, and call :meth:`unsubscribe` on disconnect. Telemetry is
    best-effort: decode/fan-out failures are logged and never propagate to clients.
    """

    def __init__(self, redis_url: str, queue_maxsize: int) -> None:
        """
        Initialize the broadcaster (opens no connection — call :meth:`start` in the lifespan).

        Args:
            redis_url (str): Redis DSN for the dedicated pub/sub connection.
            queue_maxsize (int): Bound for each per-client fan-out queue (drop-oldest on overflow).
        """
        LoggerClass.__init__(self)
        self._redis_url = redis_url
        self._queue_maxsize = queue_maxsize
        self._redis: Redis | None = None
        self._pubsub: Any = None
        self._task: asyncio.Task | None = None
        self._subscribers: set[asyncio.Queue] = set()

    def __decode(self, data: Any) -> dict | None:
        """Decode a raw Redis message payload into an event dict, or None on malformed input."""
        try:
            if isinstance(data, (bytes, bytearray)):
                data = data.decode("utf-8")
            return json.loads(data)
        except (ValueError, UnicodeDecodeError) as exc:
            self.logger.warning(f"Dropping malformed event payload ({exc}).")
            return None

    def __fan_out(self, event: dict) -> None:
        """Push an event onto every subscriber queue, dropping the oldest item when one is full."""
        # Snapshot the set: a subscriber may unsubscribe concurrently between events.
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Slow/stuck client: discard its oldest event to make room for the newest.
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass
                self.logger.debug(f"Subscriber queue full — dropped oldest event.")

    async def _run(self) -> None:
        """
        Read the subscription forever and fan out each decoded message, self-healing on drop.

        A lost Redis connection must not silently kill fan-out: the browser→backend SSE link stays
        open, so the frontend's ``onerror`` fallback never fires. We therefore catch broker errors
        and resubscribe with capped exponential backoff. Cancellation (shutdown) always propagates.
        """
        backoff = _RESUBSCRIBE_BACKOFF_INITIAL_S
        while True:
            try:
                # 1. listen() yields control messages too — only forward actual 'message' frames
                async for message in self._pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    event = self.__decode(message["data"])
                    if event is not None:
                        self.__fan_out(event)
                # listen() returning means the connection closed — fall through to resubscribe.
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.warning(f"Broadcaster subscription error ({exc}); resubscribing soon.")

            # 2. Re-establish the subscription after a drop; back off and retry on repeated failure.
            try:
                await asyncio.sleep(backoff)
                await self._pubsub.subscribe(EVENTS_CHANNEL)
                backoff = _RESUBSCRIBE_BACKOFF_INITIAL_S
                self.logger.info(f"Broadcaster resubscribed to '{EVENTS_CHANNEL}'.")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.warning(f"Broadcaster resubscribe failed ({exc}); backing off.")
                backoff = min(backoff * 2, _RESUBSCRIBE_BACKOFF_MAX_S)

    async def start(self) -> None:
        """Open the dedicated connection, subscribe to the channel, and launch the fan-out task."""
        # 1. Idempotent — a second call while running is a no-op
        if self._task is not None:
            return

        # 2. Dedicated client: subscribe mode forbids other commands, so never reuse the arq pool
        self._redis = Redis.from_url(self._redis_url)
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(EVENTS_CHANNEL)

        # 3. Background loop fans messages out to subscriber queues
        self._task = asyncio.create_task(self._run(), name="event-broadcaster")
        self.logger.info(f"EventBroadcaster subscribed to '{EVENTS_CHANNEL}'.")

    async def stop(self) -> None:
        """Cancel the fan-out task and close the pub/sub + dedicated connection. Never raises."""
        # 1. Cancel the background loop and await its teardown
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # 2. Close the pub/sub channel, then the dedicated client — swallow shutdown errors
        if self._pubsub is not None:
            try:
                await self._pubsub.unsubscribe(EVENTS_CHANNEL)
                await self._pubsub.aclose()
            except Exception as exc:
                self.logger.warning(f"Error closing pub/sub ({exc}).")
            self._pubsub = None
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception as exc:
                self.logger.warning(f"Error closing broadcaster Redis client ({exc}).")
            self._redis = None
        self.logger.info(f"EventBroadcaster stopped.")

    def subscribe(self) -> asyncio.Queue:
        """
        Register a new client and return its bounded fan-out queue.

        Returns:
            asyncio.Queue: A queue receiving every subsequent event (drop-oldest when full).
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_maxsize)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """
        Deregister a client queue so it no longer receives events.

        Args:
            queue (asyncio.Queue): The queue previously returned by :meth:`subscribe`.
        """
        self._subscribers.discard(queue)


# ------------------- Public API ------------------- #
__all__ = ["EventBroadcaster"]

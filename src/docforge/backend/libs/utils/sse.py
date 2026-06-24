# ====== Code Summary ======
# SseHelpers — static helpers that turn the EventBroadcaster fan-out into an SSE response.
# Builds the async generator (subscribe → yield matching events → unsubscribe on disconnect) and
# the per-collection filter predicate. Shared by the global monitoring stream and the
# collection-scoped documents stream so both routes stay thin (brique C).

# ====== Standard Library Imports ======
from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from sse_starlette.sse import EventSourceResponse

# ====== Internal Project Imports ======
from libs.observability.events import EventBroadcaster, EventType


class SseHelpers:
    """Static helpers building SSE responses from the shared EventBroadcaster."""

    logger = loggerplusplus.bind(identifier="SseHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("SseHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def collection_predicate(collection_id: str) -> Callable[[dict], bool]:
        """
        Build a predicate keeping only events that concern a given collection.

        ``job.updated`` carries ``collection_id`` under ``job``; ``stage.progress`` carries it at
        the top level (enriched in brique C). All other event types are document-irrelevant and
        excluded from the document-scoped stream.

        Args:
            collection_id (str): The collection to filter on.

        Returns:
            Callable[[dict], bool]: Predicate returning True when the event matches the collection.
        """

        def _match(event: dict) -> bool:
            # 1. Job lifecycle events nest their fields under "job"
            if event.get("type") == EventType.JOB_UPDATED:
                return (event.get("job") or {}).get("collection_id") == collection_id
            # 2. Stage progress events carry the collection id at the top level
            if event.get("type") == EventType.STAGE_PROGRESS:
                return event.get("collection_id") == collection_id
            # 3. Worker/batch events are not document-scoped
            return False

        return _match

    @staticmethod
    def stream(
        broadcaster: EventBroadcaster,
        *,
        keepalive: int,
        predicate: Callable[[dict], bool] | None = None,
    ) -> EventSourceResponse:
        """
        Build an SSE response streaming broadcaster events to one client.

        Args:
            broadcaster (EventBroadcaster): The shared fan-out hub to subscribe to.
            keepalive (int): Comment-ping interval in seconds (proxy keep-alive).
            predicate (Callable[[dict], bool] | None): Optional filter; when None, all events pass.

        Returns:
            EventSourceResponse: A streaming response; unsubscribes automatically on disconnect.
        """
        # 1. Register this client's bounded queue up front so no event is missed before first yield
        queue = broadcaster.subscribe()

        async def _generator() -> AsyncIterator[dict]:
            # 2. Always unsubscribe on disconnect (CancelledError / GeneratorExit) to free the queue
            try:
                while True:
                    event = await queue.get()
                    if predicate is None or predicate(event):
                        yield {"event": event.get("type", "message"), "data": json.dumps(event)}
            finally:
                broadcaster.unsubscribe(queue)

        # 3. sse-starlette emits its own keep-alive pings and cancels the generator on disconnect
        return EventSourceResponse(_generator(), ping=keepalive)


# ------------------- Public API ------------------- #
__all__ = ["SseHelpers"]

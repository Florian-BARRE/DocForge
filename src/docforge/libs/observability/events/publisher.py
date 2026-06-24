# ====== Code Summary ======
# EventPublisher — publishes typed monitoring events onto the single Redis pub/sub channel.
# Used by the worker (job/stage events) and can be reused by the backend. Publishing with no
# subscriber is a harmless no-op in Redis, so brique A can publish before brique C consumes.

# ====== Standard Library Imports ======
from __future__ import annotations

import json
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from redis.asyncio import Redis

# ====== Local Project Imports ======
from .channels import EVENTS_CHANNEL, EventType


class EventPublisher(LoggerClass):
    """
    Publishes monitoring events to the shared Redis channel.

    Each event is a JSON object ``{"type": <EventType>, ...payload}``. Failures to publish are
    logged and swallowed: telemetry must never break the pipeline it observes.
    """

    def __init__(self, redis: Redis) -> None:
        """
        Initialize the publisher.

        Args:
            redis (Redis): Async Redis client (arq's ``ArqRedis`` is a subclass).
        """
        LoggerClass.__init__(self)
        self._redis = redis

    async def publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """
        Publish a typed event onto the monitoring channel.

        Args:
            event_type (EventType): Event discriminator.
            payload (dict): Event body (merged with the ``type`` field).
        """
        # 1. Telemetry is best-effort — never let a publish failure surface into the pipeline
        try:
            message = json.dumps({"type": str(event_type), **payload})
            await self._redis.publish(EVENTS_CHANNEL, message)
        except Exception as exc:
            self.logger.warning(f"Failed to publish {event_type} event ({exc}).")

    async def job_updated(self, job: dict[str, Any]) -> None:
        """Publish a ``job.updated`` event carrying the job snapshot."""
        await self.publish(EventType.JOB_UPDATED, {"job": job})

    async def stage_progress(
        self,
        job_id: str,
        stage: str,
        progress: int,
        collection_id: str | None = None,
        document_id: str | None = None,
    ) -> None:
        """
        Publish a ``stage.progress`` event for a running job.

        ``collection_id``/``document_id`` let the SSE layer (brique C) scope progress to a single
        collection's document stream; they are optional so non-collection runs still publish.
        """
        await self.publish(
            EventType.STAGE_PROGRESS,
            {
                "job_id": job_id,
                "stage": stage,
                "progress": progress,
                "collection_id": collection_id,
                "document_id": document_id,
            },
        )

    async def worker_heartbeat(self, heartbeat: dict[str, Any]) -> None:
        """Publish a ``worker.heartbeat`` event carrying the heartbeat snapshot."""
        await self.publish(EventType.WORKER_HEARTBEAT, {"worker": heartbeat})


# ------------------- Public API ------------------- #
__all__ = ["EventPublisher"]

# ====== Code Summary ======
# HeartbeatReader — used by the backend to list all live workers by reading their TTL'd
# heartbeat keys from Redis. The scan is bounded by the number of workers (tiny), so it is cheap
# enough to call per monitoring request.

# ====== Standard Library Imports ======
from __future__ import annotations

import json

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from redis.asyncio import Redis

# ====== Local Project Imports ======
from .models import WORKER_KEY_PREFIX, WorkerHeartbeat


class HeartbeatReader(LoggerClass):
    """
    Reads all live worker heartbeats from Redis.

    Lives in the backend process. Only keys that still exist (TTL not expired) are returned, so
    dead workers naturally drop out of the list.
    """

    def __init__(self, redis: Redis) -> None:
        """
        Initialize the reader.

        Args:
            redis (Redis): Async Redis client (arq's ``ArqRedis`` is a subclass).
        """
        LoggerClass.__init__(self)
        self._redis = redis

    async def list_workers(self) -> list[WorkerHeartbeat]:
        """
        Return every currently-live worker heartbeat.

        Returns:
            list[WorkerHeartbeat]: One entry per non-expired ``docforge:worker:*`` key,
            ordered by ``worker_id`` for stable display.
        """
        # 1. Collect live heartbeat keys (SCAN — bounded by worker count, never KEYS)
        keys: list[bytes | str] = []
        async for key in self._redis.scan_iter(match=f"{WORKER_KEY_PREFIX}*"):
            keys.append(key)
        if not keys:
            return []

        # 2. Bulk-fetch payloads in one round-trip
        raw_values = await self._redis.mget(keys)

        # 3. Parse each payload, tolerating a key that expired between SCAN and MGET (None)
        workers: list[WorkerHeartbeat] = []
        for raw in raw_values:
            if raw is None:
                continue
            try:
                payload = json.loads(raw)
                workers.append(WorkerHeartbeat.from_dict(payload))
            except (ValueError, TypeError) as exc:
                self.logger.warning(f"Skipping malformed heartbeat payload ({exc}).")

        # 4. Stable ordering for the dashboard
        workers.sort(key=lambda w: w.worker_id)
        return workers


# ------------------- Public API ------------------- #
__all__ = ["HeartbeatReader"]

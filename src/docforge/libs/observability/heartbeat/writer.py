# ====== Code Summary ======
# HeartbeatWriter — used by each worker process to publish its liveness/load snapshot to Redis
# under a TTL'd key. The TTL (≈ 3x the write interval) means a crashed worker's key expires on
# its own, so the monitoring layer never shows a dead worker as alive for long.

# ====== Standard Library Imports ======
from __future__ import annotations

import json

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from redis.asyncio import Redis

# ====== Local Project Imports ======
from .models import WORKER_KEY_PREFIX, WorkerHeartbeat


class HeartbeatWriter(LoggerClass):
    """
    Writes a worker's heartbeat to Redis with a TTL.

    One instance per worker process. ``beat`` is called on every heartbeat tick; the TTL is
    refreshed each time, so the key survives only as long as the worker keeps beating.
    """

    def __init__(self, redis: Redis, worker_id: str, ttl_s: int) -> None:
        """
        Initialize the writer.

        Args:
            redis (Redis): Async Redis client (arq's ``ArqRedis`` is a subclass).
            worker_id (str): Stable id of the owning worker process.
            ttl_s (int): Key time-to-live in seconds (≈ 3x heartbeat interval).
        """
        LoggerClass.__init__(self)
        self._redis = redis
        self._worker_id = worker_id
        self._ttl_s = ttl_s
        self._key = f"{WORKER_KEY_PREFIX}{worker_id}"

    async def beat(self, heartbeat: WorkerHeartbeat) -> None:
        """
        Write the heartbeat snapshot, refreshing the TTL.

        Args:
            heartbeat (WorkerHeartbeat): Current liveness/load snapshot.
        """
        # 1. Serialize + SET with expiry (SET ... EX ttl) so the key self-expires on crash
        await self._redis.set(self._key, json.dumps(heartbeat.to_dict()), ex=self._ttl_s)

    async def remove(self) -> None:
        """Delete the heartbeat key on graceful shutdown (best-effort)."""
        # 1. Drop the key so a clean shutdown disappears immediately rather than after the TTL
        await self._redis.delete(self._key)


# ------------------- Public API ------------------- #
__all__ = ["HeartbeatWriter"]

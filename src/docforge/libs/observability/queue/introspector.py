# ====== Code Summary ======
# QueueIntrospector — read-only view over the arq job queue stored in Redis.
# Never mutates any arq:* key. Surfaces queue depth and per-job arq status to the
# monitoring endpoints without breaking arq's own contract.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from arq.constants import default_queue_name, in_progress_key_prefix
from arq.jobs import Job
from loggerplusplus import LoggerClass
from redis.asyncio import Redis

# arq Redis keys (read-only). Aliased from arq's own constants so they never drift on upgrade.
# The default queue is a sorted set scored by run-at epoch ms; each picked-up job gets a
# short-lived ``arq:in-progress:<id>`` key with a TTL.
ARQ_QUEUE_KEY: str = default_queue_name
ARQ_IN_PROGRESS_PREFIX: str = in_progress_key_prefix


class QueueIntrospector(LoggerClass):
    """
    Read-only introspection of the arq queue.

    Exposes the cheap, contract-safe primitives the monitoring layer needs: queued depth
    (``ZCARD``), a single job's arq-side status, and (diagnostic only) the set of in-progress
    job ids. Counts of running/done/failed jobs come from Postgres, not from here.
    """

    def __init__(self, redis: Redis) -> None:
        """
        Initialize the introspector.

        Args:
            redis (Redis): Async Redis client (arq's ``ArqRedis`` is a subclass).
        """
        LoggerClass.__init__(self)
        self._redis = redis

    async def queue_depth(self) -> int:
        """
        Return the number of queued (pending) jobs in the default arq queue.

        Returns:
            int: Cardinality of the ``arq:queue`` sorted set (O(1) ``ZCARD``).
        """
        # 1. ZCARD is O(1) — cheaper than deserializing every queued job
        return int(await self._redis.zcard(ARQ_QUEUE_KEY))

    async def job_arq_status(self, job_id: str) -> str:
        """
        Return the arq-side status of a single job.

        Args:
            job_id (str): The arq job id (DocForge passes ``_job_id=str(job_uuid)``).

        Returns:
            str: One of ``deferred|queued|in_progress|complete|not_found``.
        """
        # 1. Delegate to arq's own status resolver (checks result/in-progress/queue keys)
        status = await Job(job_id, redis=self._redis).status()
        return str(status.value)

    async def in_progress_ids(self) -> list[str]:
        """
        Return the ids of jobs currently in progress across all workers (diagnostic only).

        Uses a non-blocking ``SCAN`` over the volatile ``arq:in-progress:*`` keys. This is the
        only way arq exposes cross-worker in-flight jobs; it is O(N) over those keys, so it is
        kept off the hot path (running counts come from Postgres instead).

        Returns:
            list[str]: Job ids with a live in-progress marker.
        """
        # 1. SCAN (never KEYS) so a large keyspace does not block Redis
        ids: list[str] = []
        async for key in self._redis.scan_iter(match=f"{ARQ_IN_PROGRESS_PREFIX}*"):
            text = key.decode() if isinstance(key, (bytes, bytearray)) else str(key)
            ids.append(text.removeprefix(ARQ_IN_PROGRESS_PREFIX))
        return ids


# ------------------- Public API ------------------- #
__all__ = ["QueueIntrospector", "ARQ_QUEUE_KEY", "ARQ_IN_PROGRESS_PREFIX"]

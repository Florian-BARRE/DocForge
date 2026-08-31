# ====== Code Summary ======
# QueueClient — the backend's ONLY contact with Redis: enqueue ingestion jobs (ids only, the
# worker rehydrates everything). The pool is created LAZILY on first use so the app boots and
# serves its design surface without Redis; the connection error surfaces exactly where Redis
# is genuinely required (an upload), never at startup.

# ====== Standard Library Imports ======
import asyncio

# ====== Third-Party Library Imports ======
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======


class QueueClient(LoggerClass):
    """Lazy arq pool + the typed enqueue calls the routers use."""

    def __init__(self, redis_url: str) -> None:
        """
        Args:
            redis_url (str): The Redis DSN the worker listens on.
        """
        LoggerClass.__init__(self)
        self._settings = RedisSettings.from_dsn(redis_url)
        self._pool: ArqRedis | None = None
        # Serialises the first-use pool creation so two concurrent requests never race two pools.
        self._pool_lock = asyncio.Lock()

    async def __get_pool(self) -> ArqRedis:
        """Create the pool on first use (kept for the app's lifetime), race-free."""
        # 1. Fast path — the pool already exists, no lock contention.
        if self._pool is not None:
            return self._pool

        # 2. Serialise creation; re-check inside the lock (double-checked locking) so only the
        #    first waiter creates the pool and the rest reuse it.
        async with self._pool_lock:
            if self._pool is None:
                self._pool = await create_pool(self._settings)
                self.logger.info(f"Queue pool connected")
        return self._pool

    async def enqueue_ingest(self, document_id: str, job_id: str) -> None:
        """
        Enqueue one ingestion — the message carries IDS ONLY (retry-safe, light).

        The per-collection wall-clock budget is NOT an enqueue concern. arq has no per-message job
        timeout (``enqueue_job`` only accepts ``_job_id``/``_queue_name``/``_defer_*``/``_expires``),
        so the worker reads ``collection.job_timeout_seconds`` itself and hands it to the engine as
        the run's clean internal timeout; arq's uniform worker-level ``job_timeout`` is the outer
        backstop for every job. (A per-collection budget larger than the worker's global timeout is
        therefore capped by it — raise WORKER_JOB_TIMEOUT_SECONDS if you need bigger budgets.)

        Args:
            document_id (str): The admitted document's UUID.
            job_id (str): The job row driving the lifecycle.
        """
        pool = await self.__get_pool()
        await pool.enqueue_job("ingest_document", document_id, job_id)
        self.logger.info(f"Enqueued ingestion for document {document_id} (job {job_id})")

    async def enqueue_backfill(self, collection_id: str) -> None:
        """
        Enqueue the two collection-wide backfill repairs (filter payloads + meta vectors).

        The store-side repair after a schema edit made a field filterable/semantic: existing points
        get the newly denormalised values/vectors WITHOUT a content re-embed. Both tasks are
        idempotent (pure set_payload / partial vector update), so a spurious re-enqueue is harmless.

        Args:
            collection_id (str): The collection to backfill (UUID as string, the queue carries strings).
        """
        pool = await self.__get_pool()
        await pool.enqueue_job("backfill_collection_filters", collection_id)
        await pool.enqueue_job("backfill_collection_meta_vectors", collection_id)
        self.logger.info(f"Enqueued filter + meta-vector backfill for collection {collection_id}")

    async def close(self) -> None:
        """Close the pool if it was ever opened."""
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None


__all__ = ["QueueClient"]

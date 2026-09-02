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
from arq.constants import default_queue_name
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.observability import CorrelationContext


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

    def __correlation_kwargs(self) -> dict[str, str]:
        """
        Return the ambient request's correlation id as a task kwarg, or empty when none is bound.

        The id is bound by RequestIdMiddleware and read here from the shared ContextVar — enqueue
        always happens inside the request's async context, so no router needs to thread it through.
        It rides as a NORMAL ``correlation_id`` task kwarg (never a reserved arq control kwarg like
        ``_expires``), which the worker's ``with_correlation`` wrapper consumes to rebind the same id
        for the job's logs. Empty when unbound (e.g. a background enqueue) → the worker mints its own.

        Returns:
            dict[str, str]: ``{"correlation_id": <id>}`` or ``{}``.
        """
        correlation_id = CorrelationContext.get()
        return {"correlation_id": correlation_id} if correlation_id else {}

    async def enqueue_ingest(self, document_id: str, job_id: str, force: bool = False) -> None:
        """
        Enqueue one ingestion — the message carries IDS ONLY (retry-safe, light).

        The per-collection wall-clock budget is NOT an enqueue concern. arq has no per-message job
        timeout (``enqueue_job`` only accepts ``_job_id``/``_queue_name``/``_defer_*``/``_expires``),
        so the worker reads ``collection.job_timeout_seconds`` itself and hands it to the engine as
        the run's clean internal timeout; arq's uniform worker-level ``job_timeout`` (derived from
        the worker's WORKER_JOB_TIMEOUT_MAX_SECONDS hard ceiling) is the outer backstop. A
        per-collection budget up to that ceiling is authoritative; one ABOVE it fails fast on the
        worker (named), never silently truncated — raise WORKER_JOB_TIMEOUT_MAX_SECONDS for bigger.

        Args:
            document_id (str): The admitted document's UUID.
            job_id (str): The job row driving the lifecycle.
            force (bool): When True, ride a ``force`` task kwarg so the worker skips the stage cache
                (a full recompute). A normal task kwarg, never a reserved arq control kwarg.
        """
        pool = await self.__get_pool()
        await pool.enqueue_job(
            "ingest_document", document_id, job_id, force=force, **self.__correlation_kwargs()
        )
        self.logger.info(
            f"Enqueued ingestion for document {document_id} (job {job_id}, force={force})"
        )

    async def enqueue_export(self, collection_id: str, transfer_id: str) -> None:
        """
        Enqueue one collection EXPORT — the message carries IDS ONLY (retry-safe, light).

        Mirrors ``enqueue_ingest``: no arq control kwarg (``_job_timeout`` and friends) ever rides the
        wire — arq would serialize an unknown kwarg as a task argument and crash ``export_collection``.
        The worker drives the pre-created ``collection_transfer`` row through its lifecycle.

        Args:
            collection_id (str): The collection to export (UUID as string; the queue carries strings).
            transfer_id (str): The pre-created tracking row's id (UUID as string).
        """
        pool = await self.__get_pool()
        await pool.enqueue_job(
            "export_collection", collection_id, transfer_id, **self.__correlation_kwargs()
        )
        self.logger.info(f"Enqueued export for collection {collection_id} (transfer {transfer_id})")

    async def enqueue_import(self, s3_key: str, transfer_id: str, target_name: str | None) -> None:
        """
        Enqueue one collection IMPORT — the message carries IDS/SCALARS ONLY (retry-safe, light).

        The uploaded bundle is already staged in S3 under ``s3_key``; the worker downloads, validates
        and restores it as a brand-new collection. As with every enqueue call, NO arq control kwarg is
        passed (an unknown kwarg lands as a task argument and crashes ``import_collection``).

        Args:
            s3_key (str): The staged bundle's object key in S3.
            transfer_id (str): The pre-created tracking row's id (UUID as string).
            target_name (str | None): Optional name for the new collection (collision → renamed).
        """
        pool = await self.__get_pool()
        await pool.enqueue_job(
            "import_collection", s3_key, transfer_id, target_name, **self.__correlation_kwargs()
        )
        self.logger.info(f"Enqueued import from {s3_key} (transfer {transfer_id})")

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
        correlation_kwargs = self.__correlation_kwargs()
        await pool.enqueue_job("backfill_collection_filters", collection_id, **correlation_kwargs)
        await pool.enqueue_job(
            "backfill_collection_meta_vectors", collection_id, **correlation_kwargs
        )
        self.logger.info(f"Enqueued filter + meta-vector backfill for collection {collection_id}")

    async def queue_depth(self) -> int:
        """
        Return the arq queue backlog — jobs enqueued but not yet claimed by a worker.

        arq holds queued job ids in a Redis sorted set (the default queue name); its cardinality is the
        unclaimed backlog (a worker removes the id from this set the moment it claims the job). Read for
        the /metrics ``docforge_arq_queue_depth`` gauge.

        Returns:
            int: The number of queued, unclaimed jobs (0 when the queue is empty).
        """
        # 1. One Redis round-trip: the queue sorted set's cardinality is the pending backlog.
        pool = await self.__get_pool()
        return int(await pool.zcard(default_queue_name))

    async def close(self) -> None:
        """Close the pool if it was ever opened."""
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None


__all__ = ["QueueClient"]

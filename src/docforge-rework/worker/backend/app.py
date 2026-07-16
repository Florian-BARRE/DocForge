# ====== Code Summary ======
# Worker factory — the mirror of the app's create_app(): assembles the arq WorkerSettings class
# (the long-lived queue server definition: task functions, lifecycle hooks, Redis connection,
# parallelism and timeouts). No business logic here; only wiring.

# ====== Third-Party Library Imports ======
from arq.connections import RedisSettings

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG

# ====== Local Project Imports ======
from .libs.jobs import backfill_collection_filters, ingest_document
from .lifespan import shutdown, startup


def create_worker_settings() -> type:
    """
    Assemble the arq worker definition — what `arq entrypoint.WorkerSettings` runs forever.

    Returns:
        type: The WorkerSettings class (task functions, lifecycle, queue and limits).
    """

    class WorkerSettings:
        """The queue server: listens on Redis, runs up to max_jobs tasks in parallel."""

        functions = [ingest_document, backfill_collection_filters]
        on_startup = startup
        on_shutdown = shutdown
        redis_settings = RedisSettings.from_dsn(RUNTIME_CONFIG.REDIS_URL)
        max_jobs = RUNTIME_CONFIG.WORKER_CONCURRENCY
        # arq's own cap sits ABOVE the engine's per-run timeout (the engine cancels first).
        job_timeout = RUNTIME_CONFIG.WORKER_JOB_TIMEOUT_SECONDS + 60

    return WorkerSettings


__all__ = ["create_worker_settings"]

# ====== Code Summary ======
# Worker factory — the mirror of the app's create_app(): assembles the arq WorkerSettings class
# (the long-lived queue server definition: task functions, lifecycle hooks, Redis connection,
# parallelism and timeouts). No business logic here; only wiring.

# ====== Third-Party Library Imports ======
from arq import cron
from arq.connections import RedisSettings

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG

# ====== Local Project Imports ======
from .libs.jobs import (
    backfill_collection_filters,
    backfill_collection_meta_vectors,
    export_collection,
    import_collection,
    ingest_document,
    reap_stuck_jobs,
)
from .lifespan import shutdown, startup


def create_worker_settings() -> type:
    """
    Assemble the arq worker definition — what `arq entrypoint.WorkerSettings` runs forever.

    Returns:
        type: The WorkerSettings class (task functions, lifecycle, queue and limits).
    """
    # The stuck-job reaper runs every WORKER_REAP_INTERVAL_MINUTES AND once at startup, so a wedge
    # left by the previous (crashed/hot-reloaded) run is cleared immediately. Disabled -> no cron.
    reap_minutes = set(range(0, 60, RUNTIME_CONFIG.WORKER_REAP_INTERVAL_MINUTES))
    reaper_crons = (
        [cron(reap_stuck_jobs, minute=reap_minutes, run_at_startup=True)]
        if RUNTIME_CONFIG.WORKER_REAP_ENABLED
        else []
    )

    class WorkerSettings:
        """The queue server: listens on Redis, runs up to max_jobs tasks in parallel."""

        functions = [
            ingest_document,
            backfill_collection_filters,
            backfill_collection_meta_vectors,
            export_collection,
            import_collection,
        ]
        cron_jobs = reaper_crons
        on_startup = startup
        on_shutdown = shutdown
        redis_settings = RedisSettings.from_dsn(RUNTIME_CONFIG.REDIS_URL)
        max_jobs = RUNTIME_CONFIG.WORKER_CONCURRENCY
        # arq's UNIFORM worker-level cap = the global budget + grace, a backstop ABOVE the engine's
        # per-collection timeout (which fires first, per collection). arq has no per-message timeout,
        # so this same cap applies to every job; a per-collection budget above it is capped by it.
        job_timeout = (
            RUNTIME_CONFIG.WORKER_JOB_TIMEOUT_SECONDS
            + RUNTIME_CONFIG.WORKER_JOB_TIMEOUT_GRACE_SECONDS
        )
        # Write a health record to Redis on this interval; `arq entrypoint.WorkerSettings --check`
        # reads it and exits non-zero when stale — the container healthcheck for a wedged worker.
        health_check_interval = RUNTIME_CONFIG.WORKER_HEALTH_CHECK_INTERVAL_SECONDS

    return WorkerSettings


__all__ = ["create_worker_settings"]

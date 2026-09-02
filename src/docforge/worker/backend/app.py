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
    gc_artifact_cache,
    gc_audit_log,
    gc_expired_transfers,
    gc_idempotency_keys,
    import_collection,
    ingest_document,
    reap_stuck_jobs,
    with_correlation,
)
from .lifespan import shutdown, startup


def create_worker_settings() -> type:
    """
    Assemble the arq worker definition — what `arq entrypoint.WorkerSettings` runs forever.

    Returns:
        type: The WorkerSettings class (task functions, lifecycle, queue and limits).
    """
    # Every task + cron is wrapped in `with_correlation` at this boundary (the worker's mirror of the
    # app's RequestIdMiddleware): it binds the enqueued correlation id — or a freshly-minted one for a
    # cron job — for the whole execution so the job's logs are correlatable with the request that
    # triggered it. `functools.wraps` preserves each function's name, so arq still registers/dispatches
    # them under their original names (matching the string names QueueClient enqueues).

    # The stuck-job reaper runs every WORKER_REAP_INTERVAL_MINUTES AND once at startup, so a wedge
    # left by the previous (crashed/hot-reloaded) run is cleared immediately. Disabled -> no cron.
    reap_minutes = set(range(0, 60, max(1, RUNTIME_CONFIG.WORKER_REAP_INTERVAL_MINUTES)))
    reaper_crons = (
        [cron(with_correlation(reap_stuck_jobs), minute=reap_minutes, run_at_startup=True)]
        if RUNTIME_CONFIG.WORKER_REAP_ENABLED
        else []
    )
    # The transfer GC reclaims expired export bundles (S3 object + row) every
    # WORKER_TRANSFER_GC_INTERVAL_MINUTES AND once at startup. Disabled -> no cron.
    gc_minutes = set(range(0, 60, max(1, RUNTIME_CONFIG.WORKER_TRANSFER_GC_INTERVAL_MINUTES)))
    transfer_gc_crons = (
        [cron(with_correlation(gc_expired_transfers), minute=gc_minutes, run_at_startup=True)]
        if RUNTIME_CONFIG.WORKER_TRANSFER_GC_ENABLED
        else []
    )
    # The audit retention sweep prunes rows older than AUDIT_RETENTION_DAYS every
    # WORKER_AUDIT_GC_INTERVAL_MINUTES AND once at startup. It is only registered when GC is enabled
    # AND retention is a positive window — with retention at 0 (keep-forever, the default) there is
    # no cron at all, so an out-of-box deployment never deletes audit history.
    audit_gc_minutes = set(range(0, 60, max(1, RUNTIME_CONFIG.WORKER_AUDIT_GC_INTERVAL_MINUTES)))
    audit_gc_crons = (
        [cron(with_correlation(gc_audit_log), minute=audit_gc_minutes, run_at_startup=True)]
        if RUNTIME_CONFIG.WORKER_AUDIT_GC_ENABLED and RUNTIME_CONFIG.AUDIT_RETENTION_DAYS > 0
        else []
    )
    # The idempotency retention sweep prunes records past their expires_at (now + IDEMPOTENCY_TTL_HOURS)
    # every WORKER_IDEMPOTENCY_GC_INTERVAL_MINUTES AND once at startup. Disabled -> no cron.
    idem_gc_minutes = set(
        range(0, 60, max(1, RUNTIME_CONFIG.WORKER_IDEMPOTENCY_GC_INTERVAL_MINUTES))
    )
    idempotency_gc_crons = (
        [cron(with_correlation(gc_idempotency_keys), minute=idem_gc_minutes, run_at_startup=True)]
        if RUNTIME_CONFIG.WORKER_IDEMPOTENCY_GC_ENABLED
        else []
    )
    # The stage-artifact cache GC evicts stale/over-cap cached parses (TTL + per-collection LRU) and
    # sweeps freed S3 blobs every WORKER_ARTIFACT_GC_INTERVAL_MINUTES AND once at startup. Disabled ->
    # no cron (an unbounded cache is not acceptable, so this is ON by default).
    artifact_gc_minutes = set(
        range(0, 60, max(1, RUNTIME_CONFIG.WORKER_ARTIFACT_GC_INTERVAL_MINUTES))
    )
    artifact_gc_crons = (
        [cron(with_correlation(gc_artifact_cache), minute=artifact_gc_minutes, run_at_startup=True)]
        if RUNTIME_CONFIG.WORKER_ARTIFACT_GC_ENABLED
        else []
    )

    class WorkerSettings:
        """The queue server: listens on Redis, runs up to max_jobs tasks in parallel."""

        functions = [
            with_correlation(ingest_document),
            with_correlation(backfill_collection_filters),
            with_correlation(backfill_collection_meta_vectors),
            with_correlation(export_collection),
            with_correlation(import_collection),
        ]
        cron_jobs = (
            reaper_crons
            + transfer_gc_crons
            + audit_gc_crons
            + idempotency_gc_crons
            + artifact_gc_crons
        )
        on_startup = startup
        on_shutdown = shutdown
        redis_settings = RedisSettings.from_dsn(RUNTIME_CONFIG.REDIS_URL)
        max_jobs = RUNTIME_CONFIG.WORKER_CONCURRENCY
        # arq's UNIFORM worker-level cap = the HARD ceiling + grace, a backstop ABOVE the engine's
        # per-collection timeout (which fires first for any budget up to the ceiling, keeping the
        # engine authoritative). arq has no per-message timeout, so this one cap applies to every
        # job; a per-collection budget ABOVE the ceiling is rejected fail-fast (never truncated here).
        job_timeout = (
            RUNTIME_CONFIG.WORKER_JOB_TIMEOUT_MAX_SECONDS
            + RUNTIME_CONFIG.WORKER_JOB_TIMEOUT_GRACE_SECONDS
        )
        # Write a health record to Redis on this interval; `arq entrypoint.WorkerSettings --check`
        # reads it and exits non-zero when stale — the container healthcheck for a wedged worker.
        health_check_interval = RUNTIME_CONFIG.WORKER_HEALTH_CHECK_INTERVAL_SECONDS

    return WorkerSettings


__all__ = ["create_worker_settings"]

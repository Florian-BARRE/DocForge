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
    gc_job_history,
    gc_trace_payloads,
    import_collection,
    ingest_document,
    reap_stuck_jobs,
    reap_stuck_transfers,
    with_correlation,
)
from .lifespan import shutdown, startup


def _cron_minutes(interval_minutes: int, offset: int) -> set[int]:
    """
    Build the minute-of-hour set for a cron firing every `interval_minutes`, phase-shifted by
    `offset` (W1-09 fix).

    The worker crons used to compute their minute set as `range(0, 60, interval)`, which always
    includes `:00` — every family therefore fired together at each hour boundary (AND most of them
    also fire once at startup), saturating the small worker pool right when real ingestion jobs also
    compete for a slot. Shifting each family's cadence by a distinct `offset` keeps every family's
    own cadence exact while spreading the families across different minutes.

    Args:
        interval_minutes (int): Cadence in minutes (clamped to >= 1 by the caller).
        offset (int): Phase shift (0-59), distinct per cron family, so siblings never share a minute.

    Returns:
        set[int]: Minutes of the hour (0-59) this cron fires on.
    """
    interval_minutes = max(1, interval_minutes)
    return {(offset + m) % 60 for m in range(0, 60, interval_minutes)}


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
    # `run_at_startup=True` is kept ONLY for this family (the reaper recovers stuck jobs/workers
    # after a restart — worth the boot-time cost); every GC family below now defers to its first
    # scheduled tick instead. Offset 2 (of 7, see `_cron_minutes`).
    reap_minutes = _cron_minutes(RUNTIME_CONFIG.WORKER_REAP_INTERVAL_MINUTES, offset=2)
    reaper_crons = (
        [
            cron(with_correlation(reap_stuck_jobs), minute=reap_minutes, run_at_startup=True),
            # Sibling sweep on the SAME cadence + switch: clears collection_transfer rows a worker
            # crash/hard-kill left RUNNING forever (the ingestion-job reaper is document-scoped and
            # does not cover them). Marks them FAILED → terminal + their staged bundle GC-reclaimable.
            cron(with_correlation(reap_stuck_transfers), minute=reap_minutes, run_at_startup=True),
        ]
        if RUNTIME_CONFIG.WORKER_REAP_ENABLED
        else []
    )
    # The transfer GC reclaims expired export bundles (S3 object + row) every
    # WORKER_TRANSFER_GC_INTERVAL_MINUTES. Disabled -> no cron. Offset 8 (of 7, see `_cron_minutes`)
    # keeps it off both the reaper's minutes above and the hourly GCs below.
    # `run_at_startup=False`: a backlog of expired-but-ungarbage-collected bundles is not urgent
    # enough to justify extra boot-time load — it waits for its first scheduled tick.
    gc_minutes = _cron_minutes(RUNTIME_CONFIG.WORKER_TRANSFER_GC_INTERVAL_MINUTES, offset=8)
    transfer_gc_crons = (
        [cron(with_correlation(gc_expired_transfers), minute=gc_minutes, run_at_startup=False)]
        if RUNTIME_CONFIG.WORKER_TRANSFER_GC_ENABLED
        else []
    )
    # The audit retention sweep prunes rows older than AUDIT_RETENTION_DAYS every
    # WORKER_AUDIT_GC_INTERVAL_MINUTES. It is only registered when GC is enabled AND retention is a
    # positive window — with retention at 0 (keep-forever, the default) there is no cron at all, so
    # an out-of-box deployment never deletes audit history.
    # Offset 20 (of 7, see `_cron_minutes`) — distinct from the reaper, the transfer GC, and the
    # other hourly GCs below. `run_at_startup=False`: retention pruning can wait for its first tick.
    audit_gc_minutes = _cron_minutes(RUNTIME_CONFIG.WORKER_AUDIT_GC_INTERVAL_MINUTES, offset=20)
    audit_gc_crons = (
        [cron(with_correlation(gc_audit_log), minute=audit_gc_minutes, run_at_startup=False)]
        if RUNTIME_CONFIG.WORKER_AUDIT_GC_ENABLED and RUNTIME_CONFIG.AUDIT_RETENTION_DAYS > 0
        else []
    )
    # The job-history retention sweep prunes TERMINAL jobs (and their cascading stage-events) older
    # than JOB_HISTORY_RETENTION_DAYS every WORKER_JOB_HISTORY_GC_INTERVAL_MINUTES. Same convention as
    # the audit GC: only registered when GC is enabled AND retention is a positive window — with
    # retention at 0 (keep-forever, the default) there is no cron at all, so an out-of-box deployment
    # never deletes job history. A job still carrying an un-GC'd full-trace payload is skipped by the
    # prune query (the trace GC reclaims those first), so this sweep never strands an object-store
    # trace namespace. Offset 14 (of 7, see `_cron_minutes`) — distinct from all siblings.
    # `run_at_startup=False`: retention pruning can wait for its first tick.
    history_gc_minutes = _cron_minutes(
        RUNTIME_CONFIG.WORKER_JOB_HISTORY_GC_INTERVAL_MINUTES, offset=14
    )
    history_gc_crons = (
        [cron(with_correlation(gc_job_history), minute=history_gc_minutes, run_at_startup=False)]
        if RUNTIME_CONFIG.WORKER_JOB_HISTORY_GC_ENABLED
        and RUNTIME_CONFIG.JOB_HISTORY_RETENTION_DAYS > 0
        else []
    )
    # The idempotency retention sweep prunes records past their expires_at (now + IDEMPOTENCY_TTL_HOURS)
    # every WORKER_IDEMPOTENCY_GC_INTERVAL_MINUTES. Disabled -> no cron.
    # Offset 35 (of 7, see `_cron_minutes`). `run_at_startup=False`: expired keys can wait for the
    # first tick — the store is a cache, so nothing is lost by a short delay.
    idem_gc_minutes = _cron_minutes(
        RUNTIME_CONFIG.WORKER_IDEMPOTENCY_GC_INTERVAL_MINUTES, offset=35
    )
    idempotency_gc_crons = (
        [cron(with_correlation(gc_idempotency_keys), minute=idem_gc_minutes, run_at_startup=False)]
        if RUNTIME_CONFIG.WORKER_IDEMPOTENCY_GC_ENABLED
        else []
    )
    # The stage-artifact cache GC evicts stale/over-cap cached parses (TTL + per-collection LRU) and
    # sweeps freed S3 blobs every WORKER_ARTIFACT_GC_INTERVAL_MINUTES. Disabled -> no cron (an
    # unbounded cache is not acceptable, so this is ON by default).
    # Offset 50 (of 7, see `_cron_minutes`). `run_at_startup=False`: the cache is bounded by its own
    # TTL/LRU caps, so an idle cache can wait for the first scheduled sweep.
    artifact_gc_minutes = _cron_minutes(
        RUNTIME_CONFIG.WORKER_ARTIFACT_GC_INTERVAL_MINUTES, offset=50
    )
    artifact_gc_crons = (
        [
            cron(
                with_correlation(gc_artifact_cache),
                minute=artifact_gc_minutes,
                run_at_startup=False,
            )
        ]
        if RUNTIME_CONFIG.WORKER_ARTIFACT_GC_ENABLED
        else []
    )
    # The trace-retention GC prefix-deletes the object-store payloads of jobs older than
    # WORKER_TRACE_RETENTION_DAYS every WORKER_TRACE_GC_INTERVAL_MINUTES. Only registered when
    # retention is a positive window — at 0 (keep-forever) there is no cron at all, so an out-of-box
    # deployment never deletes trace payloads (same convention as the audit GC).
    # Offset 44 (of 7, see `_cron_minutes`) — distinct from all siblings above.
    # `run_at_startup=False`: aged trace payloads can wait for the first scheduled sweep.
    trace_gc_minutes = _cron_minutes(RUNTIME_CONFIG.WORKER_TRACE_GC_INTERVAL_MINUTES, offset=44)
    trace_gc_crons = (
        [cron(with_correlation(gc_trace_payloads), minute=trace_gc_minutes, run_at_startup=False)]
        if RUNTIME_CONFIG.WORKER_TRACE_RETENTION_DAYS > 0
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
            + history_gc_crons
            + idempotency_gc_crons
            + artifact_gc_crons
            + trace_gc_crons
        )
        on_startup = startup
        on_shutdown = shutdown
        redis_settings = RedisSettings.from_dsn(RUNTIME_CONFIG.REDIS_URL)
        max_jobs = RUNTIME_CONFIG.WORKER_CONCURRENCY
        # No arq auto-retry. arq's default (retry_jobs=True / max_tries=5) re-delivers a job whose
        # worker crashed or was SIGTERMed mid-run — but the stuck-job reaper + the startup reclaim
        # ALREADY recover such orphans (they mark the job FAILED and its document re-ingestable), and
        # a zombie re-delivery of a job the reaper has since marked terminal is exactly the
        # spurious-cancel / document-clobber bug this closes at the root. Recovery here is explicit
        # (reaper → visibly-failed → operator/bulk reingest), never a silent retry, so automatic
        # retry is redundant AND harmful; the terminal dequeue-skip guard + mark_running's terminal
        # guard remain as defense-in-depth for any manual re-enqueue.
        retry_jobs = False
        # arq's UNIFORM worker-level cap = the HARD ceiling + grace, a backstop ABOVE the engine's
        # per-collection timeout (which fires first for any job timeout up to the ceiling, keeping the
        # engine authoritative). arq has no per-message timeout, so this one cap applies to every
        # job; a per-collection job timeout ABOVE the ceiling is rejected fail-fast (never truncated here).
        job_timeout = (
            RUNTIME_CONFIG.WORKER_JOB_TIMEOUT_MAX_SECONDS
            + RUNTIME_CONFIG.WORKER_JOB_TIMEOUT_GRACE_SECONDS
        )
        # Write a health record to Redis on this interval; `arq entrypoint.WorkerSettings --check`
        # reads it and exits non-zero when stale — the container healthcheck for a wedged worker.
        health_check_interval = RUNTIME_CONFIG.WORKER_HEALTH_CHECK_INTERVAL_SECONDS

    return WorkerSettings


__all__ = ["create_worker_settings"]

# ====== Code Summary ======
# arq WorkerSettings for the DocForge P2/P3/P4 pipeline worker.
# The startup/shutdown hooks delegate to WorkerBootstrap (worker_bootstrap.py) which builds
# all infrastructure (Postgres, S3, Qdrant, engine, provider chains) separately from the
# FastAPI application context.  The S2/S4/S5 stages are built via ProviderRegistry from a
# default PipelineConfig; the S6 embed provider is resolved per-job by StageEngine from the
# collection's embed config — see engine._build_s6_from_config.

# ====== Standard Library Imports ======
from __future__ import annotations

import asyncio

# ====== Third-Party Library Imports ======
from arq.connections import RedisSettings
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG  # MUST be first — registers sys.path
from libs.pipeline.worker.tasks import run_pipeline_task
from libs.pipeline.worker.worker_bootstrap import WorkerBootstrap

_logger = loggerplusplus.bind(identifier="ARQ_WORKER")


async def startup(ctx: dict) -> None:
    """
    arq worker startup hook — build all infrastructure needed by pipeline tasks.

    This runs once when the worker process starts.  All connections are built by
    WorkerBootstrap and stored in ``ctx`` for reuse across task executions.
    After infrastructure is ready, any jobs left in ``"running"`` state by a prior
    worker crash are detected and marked ``"failed"`` so they can be re-ingested.

    Args:
        ctx (dict): arq context dictionary — populated here, consumed in task functions.
    """
    _logger.info(f"Worker starting up…")
    await WorkerBootstrap.build(ctx)
    await _recover_stuck_jobs(ctx)

    # Start the background heartbeat loop (built in WorkerBootstrap). The task is cancelled
    # in shutdown(); its key is TTL'd so a crash without shutdown still expires cleanly.
    ctx["heartbeat_task"] = asyncio.create_task(ctx["heartbeat_loop"].run())
    _logger.info(f"Worker startup complete.")


async def _recover_stuck_jobs(ctx: dict) -> None:
    """
    Mark jobs stuck in ``"running"`` state as ``"failed"``.

    Jobs whose worker process was killed (OOM, container restart, SIGKILL) never
    transition out of ``"running"``.  On the next startup we detect them and mark
    them failed so operators know to re-ingest rather than waiting indefinitely.

    Args:
        ctx (dict): arq context dict (must contain ``postgres`` and ``job_repo``).
    """
    postgres = ctx["postgres"]
    job_repo = ctx["job_repo"]

    # 1. Collect every job still in "running" state
    async with postgres.session() as session:
        stuck = await job_repo.list_by_status(session, "running")

    if not stuck:
        return

    # 2. Mark each one as failed with an explanatory message
    _logger.warning(
        f"Worker: {len(stuck)} stuck job(s) from previous run — marking as failed."
    )
    for job in stuck:
        async with postgres.session() as session:
            await job_repo.update_status(
                session, job.id, "failed",
                error="Worker restarted — job was interrupted (crash or OOM). Re-ingest to retry.",
            )
    _logger.warning(f"Worker: stuck-job recovery complete ({len(stuck)} job(s) marked failed).")


async def shutdown(ctx: dict) -> None:
    """
    arq worker shutdown hook — close all infrastructure connections cleanly.

    Connections are closed in reverse startup order (Qdrant → S3 → Postgres) by
    WorkerBootstrap.teardown.

    Args:
        ctx (dict): arq context dictionary populated during startup.
    """
    _logger.info(f"Worker shutting down…")

    # Stop the heartbeat loop first so it removes its key and stops touching Redis before
    # the connections are torn down.
    heartbeat_task = ctx.get("heartbeat_task")
    if heartbeat_task is not None:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

    await WorkerBootstrap.teardown(ctx)
    _logger.info(f"Worker shutdown complete.")


class WorkerSettings:
    """
    arq WorkerSettings class — defines the worker's task list and Redis connection.

    The worker is started with:
        arq libs.pipeline.worker.worker.WorkerSettings
    from within the docforge application directory (/app/docforge in Docker).
    """

    # Tasks available to this worker
    functions = [run_pipeline_task]

    # Lifecycle hooks
    on_startup = startup
    on_shutdown = shutdown

    # Redis connection (reads from RUNTIME_CONFIG — config is imported at module top)
    redis_settings = RedisSettings.from_dsn(RUNTIME_CONFIG.REDIS_URL)

    # Retry policy: 3 attempts with exponential back-off (30s / 60s) before permanent failure.
    # The task raises arq.worker.Retry(defer=N) on non-final attempts; bare re-raise on the last.
    max_tries = 3

    # Hard deadline per task execution — arq aborts (raises asyncio.CancelledError) after this.
    # Prevents a hanging pipeline stage from blocking a worker slot indefinitely.
    job_timeout = 3600  # 1 hour

    # Max concurrent jobs this worker process runs (Brique A — configurable concurrency).
    max_jobs = RUNTIME_CONFIG.WORKER_MAX_JOBS

    # Enable arq job abort so POST /api/v1/jobs/{id}/cancel can interrupt queued/running jobs.
    # Without this flag arq never polls the abort set and cancellation is a silent no-op.
    allow_abort_jobs = RUNTIME_CONFIG.WORKER_ALLOW_ABORT

    # Health-check interval in seconds
    health_check_interval = 30

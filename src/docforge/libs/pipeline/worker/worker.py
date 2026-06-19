# ====== Code Summary ======
# arq WorkerSettings for the DocForge P2/P3/P4 pipeline worker.
# The startup/shutdown hooks delegate to WorkerBootstrap (worker_bootstrap.py) which builds
# all infrastructure (Postgres, S3, Qdrant, engine, provider chains) separately from the
# FastAPI application context.  The S2/S4/S5 stages are built via ProviderRegistry from a
# default PipelineConfig; the S6 embed provider is resolved per-job by StageEngine from the
# collection's embed config — see engine._build_s6_from_config.

# ====== Standard Library Imports ======
from __future__ import annotations

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

    Args:
        ctx (dict): arq context dictionary — populated here, consumed in task functions.
    """
    _logger.info(f"Worker starting up…")
    await WorkerBootstrap.build(ctx)
    _logger.info(f"Worker startup complete.")


async def shutdown(ctx: dict) -> None:
    """
    arq worker shutdown hook — close all infrastructure connections cleanly.

    Connections are closed in reverse startup order (Qdrant → S3 → Postgres) by
    WorkerBootstrap.teardown.

    Args:
        ctx (dict): arq context dictionary populated during startup.
    """
    _logger.info(f"Worker shutting down…")
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

    # Retry policy: 3 attempts before marking as permanently failed
    max_tries = 3

    # Health-check interval in seconds
    health_check_interval = 30

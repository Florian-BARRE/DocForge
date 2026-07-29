# ====== Code Summary ======
# Worker lifespan — the arq on_startup/on_shutdown pair, mirroring the app's lifespan: banner,
# runtime configuration dump, then EVERY service instantiated ONCE into CONTEXT (store clients
# wrapped by the Database facade, the pipeline runner). Shutdown closes what startup opened.

# ====== Standard Library Imports ======
import asyncio
import socket
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from pyfiglet import Figlet

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.services.db import Database
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.qdrant import QdrantClient
from shared_libs.services.db.s3 import S3Client

# ====== Local Project Imports ======
from .context import CONTEXT
from .libs.runner import PipelineRunner

# Total number of startup steps — update when adding/removing steps.
TOTAL_STEPS = 3


def log_step(step: int, message: str) -> None:
    """Log a numbered startup step."""
    CONTEXT.logger.info(f"\n[{step}/{TOTAL_STEPS}] {message}...")


async def startup(ctx: dict[str, Any]) -> None:
    """Instantiate every service ONCE for the worker's lifetime (arq on_startup)."""
    _ = ctx  # everything lives on CONTEXT — the arq dict is not our service locator
    # 1. Identity + banner.
    CONTEXT.logger = loggerplusplus.bind(identifier="WORKER")
    CONTEXT.RUNTIME_CONFIG = RUNTIME_CONFIG
    banner = "\n" + Figlet(font="slant").renderText(
        "".join(
            c for c in unicodedata.normalize("NFD", "DocForge Worker")
            if unicodedata.category(c) != "Mn"
        )
    )
    CONTEXT.logger.info(banner)

    # 2. Log the runtime configuration (secrets masked by configplusplus).
    log_step(1, "Runtime configuration")
    CONTEXT.logger.info(RUNTIME_CONFIG)

    # 2b. Bound the thread pool the heavy CPU stages run on. The pipeline's blocking stages
    #     (docling/ocr/render/chunk) dispatch via asyncio.to_thread, i.e. the loop's DEFAULT
    #     executor — unbounded at min(32, cpu+4). Replacing it with a small bounded pool isolates
    #     native work from asyncio's own blocking calls and caps concurrent docling/OCR instances,
    #     so a ForEach fan-out can't oversubscribe CPU/memory and a hung native call leaks at most
    #     WORKER_HEAVY_THREADS threads (never the whole box). A wall-clock timeout still cannot KILL
    #     an in-flight native call (Python threads aren't cancellable) — the worker healthcheck
    #     surfaces a wedged worker instead (see PROD-HARDENING.md).
    asyncio.get_running_loop().set_default_executor(
        ThreadPoolExecutor(
            max_workers=RUNTIME_CONFIG.WORKER_HEAVY_THREADS, thread_name_prefix="heavy"
        )
    )

    # 3. The stores: three clients wrapped by the Database facade (single contact point).
    log_step(2, "Store clients (Postgres / Qdrant / S3)")
    CONTEXT.s3 = S3Client(
        endpoint_url=RUNTIME_CONFIG.S3_ENDPOINT_URL,
        access_key=RUNTIME_CONFIG.S3_ACCESS_KEY,
        secret_key=RUNTIME_CONFIG.S3_SECRET_KEY,
        bucket=RUNTIME_CONFIG.S3_BUCKET,
        region=RUNTIME_CONFIG.S3_REGION,
    )
    CONTEXT.database = Database(
        postgres=PostgresClient(RUNTIME_CONFIG.POSTGRES_DSN),
        qdrant=QdrantClient(RUNTIME_CONFIG.QDRANT_URL, api_key=RUNTIME_CONFIG.QDRANT_API_KEY),
        s3=CONTEXT.s3,
    )
    # The worker writes blobs — make sure the bucket exists on a fresh volume (idempotent).
    await CONTEXT.database.ensure_object_store()

    # 4. Execution services + identity/limits.
    log_step(3, "Pipeline runner")
    CONTEXT.runner = PipelineRunner()
    CONTEXT.worker_id = socket.gethostname()
    CONTEXT.job_timeout_seconds = RUNTIME_CONFIG.WORKER_JOB_TIMEOUT_SECONDS
    CONTEXT.logger.info(
        f"Worker '{CONTEXT.worker_id}' ready — "
        f"{RUNTIME_CONFIG.WORKER_CONCURRENCY} parallel job(s), listening on the queue"
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    """Close every connection the startup opened (arq on_shutdown)."""
    _ = ctx
    if hasattr(CONTEXT, "database"):
        await CONTEXT.database.close()
    CONTEXT.logger.info(f"Worker '{getattr(CONTEXT, 'worker_id', '?')}' shut down")


__all__ = ["startup", "shutdown"]

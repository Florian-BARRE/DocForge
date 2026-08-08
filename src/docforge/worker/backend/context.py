# ====== Code Summary ======
# Typed service locator for the worker — the mirror of the app's CONTEXT. All shared services
# are accessed via CONTEXT (never passed around through arq's ctx dict); values are assigned at
# startup in lifespan.py. Never instantiated.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerPlusPlus

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.services.db import Database
from shared_libs.services.db.s3 import S3Client

# ====== Local Project Imports ======
from .libs.heartbeat import HeartbeatWriter
from .libs.runner import PipelineRunner


class CONTEXT:
    """
    Shared worker context — typed service locator.

    Type annotations only. All values are assigned at startup (lifespan.startup).
    Access via CONTEXT.<attribute> anywhere in the worker code.
    """

    # ── Core infrastructure ──
    logger: LoggerPlusPlus
    RUNTIME_CONFIG: type[RUNTIME_CONFIG]

    # ── Stores (the single contact point + the raw S3 client for original bytes) ──
    database: Database
    s3: S3Client

    # ── Execution ──
    runner: PipelineRunner
    worker_id: str
    job_timeout_seconds: float

    # ── Liveness ──
    heartbeat: HeartbeatWriter

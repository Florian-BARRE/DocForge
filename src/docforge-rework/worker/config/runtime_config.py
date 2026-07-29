# ====== Code Summary ======
# Worker runtime config — the HEAVY execution side: queue, stores and run limits. The worker's
# bootstrap twin of app/config (same shape: UTF-8 console guard, logger sinks, sys.path + the
# shared_libs alias registration); the variables differ — the worker talks to Redis/Postgres/
# Qdrant/S3, the app does not execute pipelines.

# ====== Standard Library Imports ======
import pathlib
import sys

# ====== Third-Party Library Imports ======
from configplusplus import EnvConfigLoader, env, safe_load_envs
from loggerplusplus import formats as lpp_formats
from loggerplusplus import loggerplusplus

# ====== Local Project Imports ======
from .helpers import RuntimePathHelpers

# ─── Console must speak UTF-8 (Windows defaults to cp1252 and chokes on the config dump) ───
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─── Reset logger before anything else ───
loggerplusplus.remove()

# ─── Local development: load services/docforge-rework/.env ───
# In containers the variables are injected by compose and this loads nothing.
safe_load_envs(
    path=pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent
    / "services"
    / "docforge-rework",
    verbose=False,
)


class RUNTIME_CONFIG(EnvConfigLoader):
    # ───── Paths & dirs ─────
    # PATH_ROOT_DIR resolves to src/docforge-rework/ (this file lives under worker/config/).
    PATH_ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
    PATH_ROOT_DIR_SHARED = PATH_ROOT_DIR / "shared"
    PATH_ROOT_DIR_WORKER = PATH_ROOT_DIR / "worker"

    # worker/libs → plain sys.path entry; shared/libs → the `shared_libs` package alias.
    PATH_LIBS = PATH_ROOT_DIR_WORKER / "backend" / "libs"
    PATH_SHARED_LIBS = PATH_ROOT_DIR_SHARED / "libs"

    # ───── Queue ─────
    REDIS_URL = env("REDIS_URL")

    # ───── Stores (the worker persists; the app never does) ─────
    POSTGRES_DSN = env("POSTGRES_DSN")
    QDRANT_URL = env("QDRANT_URL")
    QDRANT_API_KEY = env("QDRANT_API_KEY", required=False, default=None)
    S3_ENDPOINT_URL = env("S3_ENDPOINT_URL")
    S3_ACCESS_KEY = env("S3_ACCESS_KEY")
    S3_SECRET_KEY = env("S3_SECRET_KEY")
    S3_BUCKET = env("S3_BUCKET")
    S3_REGION = env("S3_REGION", default="us-east-1")

    # ───── Run limits ─────
    WORKER_CONCURRENCY = env("WORKER_CONCURRENCY", cast=int, default=2)
    WORKER_JOB_TIMEOUT_SECONDS = env("WORKER_JOB_TIMEOUT_SECONDS", cast=float, default=1800.0)
    # Size of the BOUNDED thread pool the heavy CPU stages (docling/ocr/render/chunk, dispatched via
    # asyncio.to_thread) run on. Bounding it isolates native work from asyncio's default executor and
    # caps concurrent native calls — so a ForEach fan-out can't spawn dozens of docling/OCR threads
    # (CPU/memory), and a hung native call leaks at most this many threads. See PROD-HARDENING.md.
    WORKER_HEAVY_THREADS = env("WORKER_HEAVY_THREADS", cast=int, default=4)

    # ───── Logging (mandatory set) ─────
    LOGGING_CONSOLE_LEVEL = env("LOGGING_CONSOLE_LEVEL")
    LOGGING_FILE_LEVEL = env("LOGGING_FILE_LEVEL")
    LOGGING_ENABLE_CONSOLE = env("LOGGING_ENABLE_CONSOLE", cast=bool)
    LOGGING_ENABLE_FILE = env("LOGGING_ENABLE_FILE", cast=bool)
    LOGGING_LPP_FORMAT = env("LOGGING_LPP_FORMAT")


# ─── Apply logging configuration AFTER class definition ───
lpp_format = getattr(
    lpp_formats,
    RUNTIME_CONFIG.LOGGING_LPP_FORMAT,
    lpp_formats.DebugFormat,
)()

if RUNTIME_CONFIG.LOGGING_ENABLE_CONSOLE:
    loggerplusplus.add(
        sink=sys.stdout,
        level=RUNTIME_CONFIG.LOGGING_CONSOLE_LEVEL,
        format=lpp_format,
    )

if RUNTIME_CONFIG.LOGGING_ENABLE_FILE:
    loggerplusplus.add(
        pathlib.Path("logs"),
        level=RUNTIME_CONFIG.LOGGING_FILE_LEVEL,
        format=lpp_format,
        rotation="1 week",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )

# ─── Register runtime import paths AFTER logger setup ───
RuntimePathHelpers.add_to_python_path(RUNTIME_CONFIG.PATH_ROOT_DIR_WORKER)
RuntimePathHelpers.add_to_python_path(RUNTIME_CONFIG.PATH_LIBS)
RuntimePathHelpers.register_package_alias(
    "shared_libs",
    RUNTIME_CONFIG.PATH_SHARED_LIBS,
)

__all__ = ["RUNTIME_CONFIG"]

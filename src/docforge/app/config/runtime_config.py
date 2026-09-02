# ====== Code Summary ======
# App (FastAPI) runtime config — extends the shared BaseRuntimeConfig with web-only
# settings the worker never needs (FastAPI, CORS, SSE fan-out, resource admission).
# Imported as `from config import RUNTIME_CONFIG` (resolves to this app's config tree).

# ====== Standard Library Imports =====

import pathlib
import sys

# ====== Third-Party Library Imports ======
from configplusplus import EnvConfigLoader, env, safe_load_envs
from loggerplusplus import formats as lpp_formats
from loggerplusplus import loggerplusplus

from .helpers import RuntimePathHelpers

# ─── Console must speak UTF-8 (Windows defaults to cp1252 and chokes on the config dump) ───
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─── Reset logger before anything else ───
loggerplusplus.remove()

# ─── Local development: load services/docforge/.env ───
# In containers the variables are injected by compose and this loads nothing.
safe_load_envs(
    path=pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent
    / "services"
    / "docforge",
    verbose=False,
)


class RUNTIME_CONFIG(EnvConfigLoader):
    # ───── Paths & dirs ─────
    # PATH_ROOT_DIR resolves to src/docforge/:
    # current file is expected to be located under config/runtime/,
    # so we go 3 levels up from this file.
    PATH_ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent.parent

    # Main project directories
    PATH_ROOT_DIR_SHARED = PATH_ROOT_DIR / "shared"
    PATH_ROOT_DIR_APP = PATH_ROOT_DIR / "app"
    PATH_ROOT_DIR_APP_BACKEND = PATH_ROOT_DIR_APP / "backend"
    PATH_ROOT_DIR_APP_FRONTEND = PATH_ROOT_DIR_APP / "frontend" / "dist"

    # Internal libraries directories
    #
    # backend/libs:
    #   Added directly to sys.path.
    #   Allows imports like:
    #       import my_backend_lib
    #
    # shared/libs:
    #   Exposed as the package alias `shared_libs`.
    #   Allows imports like:
    #       import shared_libs.xxx
    #       from shared_libs import xxx
    PATH_LIBS = PATH_ROOT_DIR_APP_BACKEND / "libs"
    PATH_SHARED_LIBS = PATH_ROOT_DIR_SHARED / "libs"

    # ───── FastAPI ─────
    FASTAPI_APP_NAME: str = env("FASTAPI_APP_NAME")
    FASTAPI_DEBUG_MODE: bool = env("FASTAPI_DEBUG_MODE", cast=bool)
    FASTAPI_CORS_ALLOWED_ORIGINS: str = env("FASTAPI_CORS_ALLOWED_ORIGINS")

    # Application version surfaced in OpenAPI docs (info.version) and the public /health endpoint.
    # Defaults from the deployment's pinned image tag (DOCFORGE_TAG — the same var compose uses to
    # select the image, injected into the app container's env), so the API advertises the version it
    # actually ships. Mirrors the worker's exact resolution (env("DOCFORGE_TAG", default="unknown"))
    # so app + worker agree. An explicit FASTAPI_APP_VERSION still wins; falls back to "unknown" when
    # neither is set (local dev), never a stale pinned number.
    FASTAPI_APP_VERSION: str = env(
        "FASTAPI_APP_VERSION",
        required=False,
        default=env("DOCFORGE_TAG", required=False, default="unknown"),
    )

    # ───── Authentication (API-key bearer, keys-only) ─────
    # OFF by default so local dev and the units suite run without credentials. When ON, every
    # /api/v1/* route requires a valid bearer key (the scalar docs + /openapi.json stay public).
    AUTH_ENABLED: bool = env("AUTH_ENABLED", cast=bool, default=False)
    # The bootstrap root key plaintext — provisioned idempotently at startup when auth is on.
    # Its name contains TOKEN, so configplusplus masks it in the startup config dump.
    AUTH_ROOT_TOKEN: str = env("AUTH_ROOT_TOKEN", required=False, default="")

    # ───── Search ─────
    # Wall-clock cap for one inline search run. Search is sub-second; this only guards a stuck or
    # cold provider (a cold CPU-hosted embedder's first encode can breach a tight cap → a 422). Raise
    # it on a slow/contended deployment; the default stays snappy.
    SEARCH_RUN_TIMEOUT_SECONDS: float = env("SEARCH_RUN_TIMEOUT_SECONDS", cast=float, default=30.0)

    # SSE poll cadence for the live job stream (poll-backed, no message bus). Short by design; kept
    # injectable so unit tests drive the generator with a zero interval.
    SSE_POLL_INTERVAL_SECONDS: float = env("SSE_POLL_INTERVAL_SECONDS", cast=float, default=0.75)

    # ───── Rate limiting (in-app, OFF by default) ─────
    # OFF out-of-box so no deployment ever breaks; enable per the prod runbook. When ON, each caller
    # may issue at most RATE_LIMIT_PER_MINUTE requests per rolling minute to /api/v1/* — the caller is
    # keyed by its API key when auth is on, else by client IP. The high-frequency job monitoring
    # subtree (live SSE stream + the UI's job/queue/worker polls) is EXEMPT so a normal UI session
    # never trips the limit. Over-budget requests get a 429 + Retry-After.
    RATE_LIMIT_ENABLED: bool = env("RATE_LIMIT_ENABLED", cast=bool, default=False)
    # The per-caller budget (requests per rolling minute). Generous by default so a normal UI session
    # never trips it; lower it to harden a publicly-exposed deployment.
    RATE_LIMIT_PER_MINUTE: int = env("RATE_LIMIT_PER_MINUTE", cast=int, default=600)
    # Trust the leftmost X-Forwarded-For hop for IP keying (auth-off mode). DocForge normally sits
    # behind a reverse proxy that sets XFF, so ON by default — the proxy MUST overwrite (never append)
    # a client-supplied XFF for this to be spoof-safe. Set false for a direct-exposure deployment
    # where XFF would be client-forgeable; the transport peer address is then used instead.
    RATE_LIMIT_TRUST_FORWARDED_FOR: bool = env(
        "RATE_LIMIT_TRUST_FORWARDED_FOR", cast=bool, default=True
    )

    # ───── Metrics (Prometheus /metrics, ON by default) ─────
    # ON out-of-box — the exposition carries NO PII, only ops counters/gauges. /metrics lives outside
    # /api/v1 so it is EXEMPT from auth (scrapers carry no bearer) and from the rate limiter; operators
    # MUST network-restrict it at the proxy/firewall (see docs/PROD-HARDENING.md). Set false to hide
    # the endpoint (it then 404s). Container CPU/RAM is the runtime's cAdvisor concern, not this app.
    METRICS_ENABLED: bool = env("METRICS_ENABLED", cast=bool, default=True)
    # Wall-clock cap for one scrape's infra-gauge refresh (arq queue depth + job/worker counts). A
    # degraded store can never wedge a scrape past this — the HTTP series and the gauge definitions
    # always render; the infra gauges simply keep their previous value for that scrape.
    METRICS_SCRAPE_TIMEOUT_SECONDS: float = env(
        "METRICS_SCRAPE_TIMEOUT_SECONDS", cast=float, default=5.0
    )

    # ───── Document grid (large-scale corpus view) ─────
    # Hard ceiling for one grid query page — the server clamps a larger requested ``limit`` down to
    # this so a client can never demand an unbounded scan of a 100k-document collection.
    CORPUS_MAX_PAGE_SIZE: int = env("CORPUS_MAX_PAGE_SIZE", cast=int, default=500)
    # Per-call cap on a bulk re-ingest fan-out: a filter selector matching MORE than this enqueues
    # only the first N (deterministic order) and reports ``capped=true`` + the total ``matched``, so a
    # single call can never silently flood the queue with 100k jobs. Raise it for a big planned re-run.
    CORPUS_MAX_REINGEST_FANOUT: int = env("CORPUS_MAX_REINGEST_FANOUT", cast=int, default=1000)

    # ───── Jobs list (monitoring view) ─────
    # Hard ceiling for one GET /jobs page — the server clamps a larger requested ``limit`` down to
    # this (and defaults to it), so a heavily re-ingested collection with thousands of job rows can
    # never be dumped unbounded in one call.
    JOBS_MAX_PAGE_SIZE: int = env("JOBS_MAX_PAGE_SIZE", cast=int, default=500)

    # A worker whose heartbeat is fresher than this reads as ``alive`` in the monitoring view. MUST
    # stay >> WORKER_HEARTBEAT_INTERVAL_SECONDS (worker beats ~every 10s): 30s = three missed ticks,
    # so a stale value means the process is gone, not merely idle.
    WORKER_ALIVE_THRESHOLD_SECONDS: int = env(
        "WORKER_ALIVE_THRESHOLD_SECONDS", cast=int, default=30
    )
    # A worker whose heartbeat froze past this cutoff is PRUNED — deleted from worker_heartbeats and
    # dropped from the live-fleet view — so a crashed worker (no clean shutdown to de-register itself)
    # eventually vanishes instead of lingering as a permanent "off" card. MUST stay comfortably above
    # WORKER_ALIVE_THRESHOLD_SECONDS so a live worker that merely missed a few beats is never deleted;
    # the gap between the two thresholds is the brief window a just-died worker still shows as "off".
    WORKER_PRUNE_STALE_SECONDS: int = env("WORKER_PRUNE_STALE_SECONDS", cast=int, default=180)

    # ───── Queue (enqueue only — the worker executes) ─────
    # The message carries IDS ONLY; the per-collection run budget is applied by the WORKER (it reads
    # collection.job_timeout_seconds and hands it to the engine). arq has no per-message timeout, so
    # the app never threads a timeout onto the enqueue — WORKER_JOB_TIMEOUT_GRACE_SECONDS lives in the
    # worker config alone (its WorkerSettings backstop), not here.
    REDIS_URL = env("REDIS_URL")

    # ───── Stores (admission writes + status/collection reads; never pipeline execution) ─────
    POSTGRES_DSN = env("POSTGRES_DSN")
    QDRANT_URL = env("QDRANT_URL")
    QDRANT_API_KEY = env("QDRANT_API_KEY", required=False, default=None)
    # Per-request Qdrant timeout; passed into QdrantClient at construction (see the client's docstring
    # for why the 5s library default is too low). Mirrors the worker config's identical knob.
    QDRANT_TIMEOUT_SECONDS: float = env("QDRANT_TIMEOUT_SECONDS", cast=float, default=60.0)
    S3_ENDPOINT_URL = env("S3_ENDPOINT_URL")
    S3_ACCESS_KEY = env("S3_ACCESS_KEY")
    S3_SECRET_KEY = env("S3_SECRET_KEY")
    S3_BUCKET = env("S3_BUCKET")
    S3_REGION = env("S3_REGION", default="us-east-1")

    # ───── Collection export/import (portable bundles) ─────
    # S3 key prefix an UPLOADED import bundle is staged under before the worker consumes it (kept
    # distinct from the worker's EXPORT_BUNDLE_PREFIX so produced exports and staged imports do not
    # collide). The staged object is content-addressed by a fresh UUID; a GC sweep of this prefix
    # reclaims bundles whose import never completed.
    IMPORT_STAGING_PREFIX = env("IMPORT_STAGING_PREFIX", default="collection-imports")
    # Hard ceiling on an uploaded import bundle. The multipart body is spooled to S3 with NO cap
    # otherwise — a single upload could fill the object store (a disk-exhaustion DoS). The spool aborts
    # with a 413 the instant the streamed size crosses this, and the partial staged object is removed.
    # Default 5 GiB; raise it for a deployment that legitimately moves very large corpora.
    IMPORT_MAX_BUNDLE_BYTES: int = env(
        "IMPORT_MAX_BUNDLE_BYTES", cast=int, default=5 * 1024 * 1024 * 1024
    )

    # ───── Logging ─────
    LOGGING_CONSOLE_LEVEL = env("LOGGING_CONSOLE_LEVEL")
    LOGGING_FILE_LEVEL = env("LOGGING_FILE_LEVEL")
    LOGGING_ENABLE_CONSOLE = env("LOGGING_ENABLE_CONSOLE", cast=bool)
    LOGGING_ENABLE_FILE = env("LOGGING_ENABLE_FILE", cast=bool)
    LOGGING_LPP_FORMAT = env("LOGGING_LPP_FORMAT")

    @classmethod
    def validate(cls) -> None:
        """
        Fail a misconfigured boot LOUDLY instead of bricking the app silently.

        Enforces two auth-related invariants at startup (call from the entrypoint before the app
        is built):

        Raises:
            RuntimeError: When ``AUTH_ENABLED`` is on but no ``AUTH_ROOT_TOKEN`` is set — an
                unrecoverable lockout, since no root key can ever be bootstrapped and every
                ``/api/v1`` route would 401 with no way back in.
        """
        # 1. Standard configplusplus validation first.
        super().validate()

        # 2. Auth ON with no root token is an unrecoverable lockout — refuse to boot.
        if cls.AUTH_ENABLED and not cls.AUTH_ROOT_TOKEN:
            raise RuntimeError(
                "AUTH_ENABLED is true but AUTH_ROOT_TOKEN is empty — no root key can be "
                "provisioned and every /api/v1 route would 401 with no recovery. Set "
                "AUTH_ROOT_TOKEN or disable AUTH_ENABLED."
            )

        # 3. Auth ON behind a wildcard CORS policy is a dangerous combination — warn loudly (the
        #    app sets allow_credentials=false, so it is not an outright lockout, only a smell).
        origins = {o.strip() for o in cls.FASTAPI_CORS_ALLOWED_ORIGINS.split(",") if o.strip()}
        if cls.AUTH_ENABLED and "*" in origins:
            loggerplusplus.bind(identifier="RUNTIME_CONFIG").warning(
                f"AUTH_ENABLED is true while CORS allows all origins ('*') — bearer-protected "
                f"routes are reachable cross-origin; pin FASTAPI_CORS_ALLOWED_ORIGINS in production"
            )


# ─── Apply logging configuration AFTER class definition ───
lpp_format = getattr(
    lpp_formats,
    RUNTIME_CONFIG.LOGGING_LPP_FORMAT,
    lpp_formats.DebugFormat,
)()

# Surface the request/job correlation id at the tail of every line. The field name here is a raw
# loguru template token (like {message}) and MUST match CorrelationContext.FIELD — shared_libs cannot
# be imported this early. The neutral "-" default is seeded below so this token always resolves; the
# real per-record value is written by CorrelationContext's patcher (installed in the entrypoint).
lpp_format = f"{lpp_format} <light-black>| cid=</light-black><cyan>{{extra[correlation_id]}}</cyan>"
loggerplusplus.configure(extra={"correlation_id": "-"})

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
RuntimePathHelpers.add_to_python_path(RUNTIME_CONFIG.PATH_LIBS)
RuntimePathHelpers.register_package_alias(
    "shared_libs",
    RUNTIME_CONFIG.PATH_SHARED_LIBS,
)

__all__ = ["RUNTIME_CONFIG"]

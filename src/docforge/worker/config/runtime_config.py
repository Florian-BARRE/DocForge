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
    # PATH_ROOT_DIR resolves to src/docforge/ (this file lives under worker/config/).
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

    # ───── Collection export/import (portable bundles) ─────
    # Stamped into a bundle's manifest as provenance (sourced from the deployment's pinned image tag).
    DOCFORGE_VERSION = env("DOCFORGE_TAG", required=False, default="unknown")
    # The S3 key prefix export bundles are published under (NOT content-addressed blobs).
    EXPORT_BUNDLE_PREFIX = env("EXPORT_BUNDLE_PREFIX", default="collection-exports")
    # Bundle compression codec: "zstd" (default) or "none".
    EXPORT_COMPRESSION = env("EXPORT_COMPRESSION", default="zstd")
    # Decompression-bomb guard on IMPORT: the extracted (uncompressed) bundle may be at most this
    # multiple of the compressed `.dcexport` size on disk (which the upload already capped at
    # IMPORT_MAX_BUNDLE_BYTES). A hostile bundle with a >1000x zstd ratio is refused mid-extraction
    # before it can fill the worker's disk, rather than after. 100 is generous for real corpora
    # (JSONL + already-compressed blobs rarely exceed ~10x) while still bounding the blast radius.
    IMPORT_MAX_DECOMPRESSION_RATIO = env("IMPORT_MAX_DECOMPRESSION_RATIO", cast=int, default=100)
    # Hard ceiling on the number of members (files) a bundle may contain — bounds inode/handle
    # exhaustion from a bundle of millions of tiny entries independently of their total size.
    IMPORT_MAX_MEMBERS = env("IMPORT_MAX_MEMBERS", cast=int, default=500_000)
    # How long an exported bundle object is retained before it may be garbage-collected (seconds).
    EXPORT_TTL_SECONDS = env("EXPORT_TTL_SECONDS", cast=int, default=604800)
    # Reclaim expired export bundles (the S3 object AND its `collection_transfer` row) on a cron —
    # without it the download route refuses an expired bundle but the bytes + row leak forever. ON by
    # default; disable to skip the sweep entirely (the cron is then not even registered).
    WORKER_TRANSFER_GC_ENABLED = env("WORKER_TRANSFER_GC_ENABLED", cast=bool, default=True)
    # Transfer-GC cron cadence (minutes): the sweep runs on every Nth minute of the hour. 15 → every
    # 15 minutes. It also runs once at startup so a backlog left while GC was off is cleared promptly.
    WORKER_TRANSFER_GC_INTERVAL_MINUTES = env(
        "WORKER_TRANSFER_GC_INTERVAL_MINUTES", cast=int, default=15
    )

    # ───── Audit-log retention ─────
    # How long an audit_log row is kept before the retention cron prunes it (DAYS). 0 = KEEP FOREVER
    # (the default): when 0 the prune cron is not even registered, so an out-of-box deployment never
    # deletes audit history. Set >0 (e.g. 365) to age out rows older than N days.
    AUDIT_RETENTION_DAYS = env("AUDIT_RETENTION_DAYS", cast=int, default=0)
    # Master switch for the audit retention sweep. ON by default, but a no-op unless AUDIT_RETENTION_DAYS
    # > 0 (with retention at 0 the cron is not registered at all). Disable to skip the sweep entirely.
    WORKER_AUDIT_GC_ENABLED = env("WORKER_AUDIT_GC_ENABLED", cast=bool, default=True)
    # Audit-GC cron cadence (minutes): the prune runs on every Nth minute of the hour. 60 → hourly. It
    # also runs once at startup so a backlog left while retention was disabled is cleared promptly.
    WORKER_AUDIT_GC_INTERVAL_MINUTES = env("WORKER_AUDIT_GC_INTERVAL_MINUTES", cast=int, default=60)

    # ───── Idempotency-key retention ─────
    # The app stamps each idempotency record with an ``expires_at`` (now + IDEMPOTENCY_TTL_HOURS); this
    # cron deletes every row past it so the table never grows unbounded. ON by default (the store is a
    # cache, not history — expired rows carry no value); disable to skip the sweep (cron not registered).
    WORKER_IDEMPOTENCY_GC_ENABLED = env("WORKER_IDEMPOTENCY_GC_ENABLED", cast=bool, default=True)
    # Idempotency-GC cron cadence (minutes): the prune runs on every Nth minute of the hour. 60 →
    # hourly. It also runs once at startup so a backlog left while the sweep was off is cleared promptly.
    WORKER_IDEMPOTENCY_GC_INTERVAL_MINUTES = env(
        "WORKER_IDEMPOTENCY_GC_INTERVAL_MINUTES", cast=int, default=60
    )

    # ───── Stage artifact cache (Phase-5 P1) ─────
    # Master switch for the per-collection stage-artifact cache. ON by default; when off (or on a
    # forced reingest) the worker builds NO cache hook, so the engine runs byte-for-byte as before —
    # nothing is read from or written to the cache. The cache is content+config+collection keyed, so a
    # wrong hit is impossible: turning it on out-of-box is safe.
    WORKER_CACHE_ENABLED = env("WORKER_CACHE_ENABLED", cast=bool, default=True)
    # The cache GC cron: evicts by TTL (LRU on last_hit_at) and a per-collection byte cap, then sweeps
    # any S3 stage-artifact blob whose last pointer was removed. ON by default; disable → no cron.
    WORKER_ARTIFACT_GC_ENABLED = env("WORKER_ARTIFACT_GC_ENABLED", cast=bool, default=True)
    # Cache-GC cron cadence (minutes): the sweep runs on every Nth minute of the hour AND once at
    # startup, so a backlog left while the sweep was off is cleared promptly. 60 → hourly.
    WORKER_ARTIFACT_GC_INTERVAL_MINUTES = env(
        "WORKER_ARTIFACT_GC_INTERVAL_MINUTES", cast=int, default=60
    )
    # Time-to-live for a cached artefact (days), measured from its last hit (else its creation). A row
    # untouched for longer is evicted. 0 disables the TTL pass (the size cap still bounds growth).
    CACHE_TTL_DAYS = env("CACHE_TTL_DAYS", cast=int, default=30)
    # Per-collection byte ceiling for cached artefacts. When a collection is over it, the
    # least-recently-used rows are evicted until it is under. 0 disables the size cap.
    CACHE_MAX_BYTES_PER_COLLECTION = env(
        "CACHE_MAX_BYTES_PER_COLLECTION", cast=int, default=5_000_000_000
    )

    # ───── Stores — client tuning ─────
    # Per-request Qdrant timeout. The qdrant-client default (5s) is too low for heavy vector upserts
    # indexed with wait=true; 60s covers a heavy batch. Passed into QdrantClient at construction.
    QDRANT_TIMEOUT_SECONDS = env("QDRANT_TIMEOUT_SECONDS", cast=float, default=60.0)

    # ───── Run limits ─────
    WORKER_CONCURRENCY = env("WORKER_CONCURRENCY", cast=int, default=2)
    WORKER_JOB_TIMEOUT_SECONDS = env("WORKER_JOB_TIMEOUT_SECONDS", cast=float, default=1800.0)
    # The HARD ceiling any single run may request: a per-collection job_timeout_seconds is honoured
    # up to this bound and REJECTED (fail-fast, named) above it — never silently truncated. arq's
    # outer job_timeout is derived from THIS value (+ grace), so the engine's per-run budget always
    # fires FIRST for any valid budget (the engine stays authoritative), while a single run can never
    # exceed max + grace. Raise this to allow bigger per-collection budgets. See PROD-HARDENING.md.
    WORKER_JOB_TIMEOUT_MAX_SECONDS = env(
        "WORKER_JOB_TIMEOUT_MAX_SECONDS", cast=float, default=7200.0
    )
    # arq's outer per-job cap must stay ABOVE the engine's run budget (the engine cancels first), so
    # arq only kills a genuinely-wedged run. Derived from the MAX budget (not the default) so a
    # per-collection budget up to the ceiling is authoritative; the app enqueue side carries no
    # timeout (arq has no per-message cap), so this WorkerSettings backstop is the sole outer bound.
    WORKER_JOB_TIMEOUT_GRACE_SECONDS = env(
        "WORKER_JOB_TIMEOUT_GRACE_SECONDS", cast=float, default=60.0
    )
    # Size of the BOUNDED thread pool the heavy CPU stages (docling/ocr/render/chunk, dispatched via
    # asyncio.to_thread) run on. Bounding it isolates native work from asyncio's default executor and
    # caps concurrent native calls — so a ForEach fan-out can't spawn dozens of docling/OCR threads
    # (CPU/memory), and a hung native call leaks at most this many threads. See PROD-HARDENING.md.
    WORKER_HEAVY_THREADS = env("WORKER_HEAVY_THREADS", cast=int, default=4)
    # Preflight every provider node's endpoint reachability after build/validate, BEFORE the first
    # spend — a wrong/unreachable base_url or a rejected key fails the job fast, having stored nothing.
    # ON by default: the stock pipeline ships only the stages reachable with the in-stack services
    # (intake/parse, contextualize, embed) — the provider-hosted stages (enrich VLM, metagen LLM)
    # ship OFF, so NO placeholder endpoint is ever in an executed graph out-of-box. The sweep then
    # only probes real, reachable nodes (gotenberg /health, bge_server), and a stage the operator
    # opts in is preflighted BEFORE its first spend — a wrong/placeholder endpoint fails fast having
    # stored nothing. Set to False only to skip reachability checks entirely. See PROD-HARDENING.md.
    WORKER_PREFLIGHT_ENABLED = env("WORKER_PREFLIGHT_ENABLED", cast=bool, default=True)

    # ───── Stuck-job reaper ─────
    # A dev worker hot-reload (or a crash) drops the in-flight arq task, but the DB job row stays
    # RUNNING forever and its document PROCESSING. Job.updated_at freezes when progress stops, so a
    # cron fails every RUNNING job idle past this threshold and releases its document to FAILED.
    # 1200s (20m) sits comfortably above the slowest observed single-doc run (~9m), so a
    # legitimately-slow-but-alive job is never falsely reaped. Set WORKER_REAP_ENABLED=false to skip
    # the reaper entirely (the cron is then not even registered).
    WORKER_REAP_ENABLED = env("WORKER_REAP_ENABLED", cast=bool, default=True)
    WORKER_REAP_STALE_SECONDS = env("WORKER_REAP_STALE_SECONDS", cast=int, default=1200)
    # A worker heartbeat frozen past this cutoff is PRUNED by the reaper cron (crashed workers that
    # never de-registered). This ran on the read path (GET /jobs/workers/live) before — a fleet-wide
    # DELETE on every poll — and now lives in the cron alone. MUST stay well above the app's
    # WORKER_ALIVE_THRESHOLD_SECONDS so a live worker that missed a few beats is never deleted; the
    # backend reads the SAME env, so the "off" window between the two thresholds is consistent.
    WORKER_PRUNE_STALE_SECONDS = env("WORKER_PRUNE_STALE_SECONDS", cast=int, default=180)
    # Reaper cron cadence (minutes): the stuck-job cron runs on every Nth minute of the hour. 5 →
    # every 5 minutes. It also runs once at startup so a wedge left by a crashed/hot-reloaded run is
    # cleared immediately.
    WORKER_REAP_INTERVAL_MINUTES = env("WORKER_REAP_INTERVAL_MINUTES", cast=int, default=5)

    # ───── Liveness cadences ─────
    # Heartbeat tick interval. Kept WELL BELOW the backend's WORKER_ALIVE_THRESHOLD_SECONDS (~30s) so
    # a live worker never flaps to "offline" between ticks, and a dead one ages past that threshold
    # within one window. The alive threshold MUST stay >> this interval (three-missed-ticks rule).
    WORKER_HEARTBEAT_INTERVAL_SECONDS = env(
        "WORKER_HEARTBEAT_INTERVAL_SECONDS", cast=int, default=10
    )
    # A human-friendly display name for this worker, surfaced next to its hostname in the fleet view.
    # Empty (the default) → the lifespan falls back to the hostname, so an unset deployment is
    # unchanged. Set it per replica (e.g. "gpu-box-1") to make "what is ingesting" legible at a glance.
    WORKER_NAME = env("WORKER_NAME", required=False, default="")
    # arq writes a health record to Redis every N seconds; `arq ... --check` reads it and exits
    # non-zero when stale — the container healthcheck that surfaces a wedged worker.
    WORKER_HEALTH_CHECK_INTERVAL_SECONDS = env(
        "WORKER_HEALTH_CHECK_INTERVAL_SECONDS", cast=int, default=30
    )

    # ───── Logging (mandatory set) ─────
    LOGGING_CONSOLE_LEVEL = env("LOGGING_CONSOLE_LEVEL")
    LOGGING_FILE_LEVEL = env("LOGGING_FILE_LEVEL")
    LOGGING_ENABLE_CONSOLE = env("LOGGING_ENABLE_CONSOLE", cast=bool)
    LOGGING_ENABLE_FILE = env("LOGGING_ENABLE_FILE", cast=bool)
    LOGGING_LPP_FORMAT = env("LOGGING_LPP_FORMAT")


# ─── Validate the reaper threshold: below a minute it would race legitimate short runs ───
if RUNTIME_CONFIG.WORKER_REAP_STALE_SECONDS < 60:
    raise ValueError(
        "WORKER_REAP_STALE_SECONDS must be >= 60 seconds "
        f"(got {RUNTIME_CONFIG.WORKER_REAP_STALE_SECONDS})."
    )

# ─── The global default budget must fit under the hard ceiling (arq's cap is derived from MAX) ───
if RUNTIME_CONFIG.WORKER_JOB_TIMEOUT_SECONDS > RUNTIME_CONFIG.WORKER_JOB_TIMEOUT_MAX_SECONDS:
    raise ValueError(
        "WORKER_JOB_TIMEOUT_SECONDS must be <= WORKER_JOB_TIMEOUT_MAX_SECONDS "
        f"(got {RUNTIME_CONFIG.WORKER_JOB_TIMEOUT_SECONDS} > "
        f"{RUNTIME_CONFIG.WORKER_JOB_TIMEOUT_MAX_SECONDS})."
    )

# ─── Apply logging configuration AFTER class definition ───
lpp_format = getattr(
    lpp_formats,
    RUNTIME_CONFIG.LOGGING_LPP_FORMAT,
    lpp_formats.DebugFormat,
)()

# Surface the request/job correlation id at the tail of every line so a job's logs share the id of
# the request that enqueued it. The field name here is a raw loguru template token (like {message})
# and MUST match CorrelationContext.FIELD — shared_libs cannot be imported this early. The neutral "-"
# default is seeded below so this token always resolves; the real per-record value is written by
# CorrelationContext's patcher (installed in the worker startup hook).
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
RuntimePathHelpers.add_to_python_path(RUNTIME_CONFIG.PATH_ROOT_DIR_WORKER)
RuntimePathHelpers.add_to_python_path(RUNTIME_CONFIG.PATH_LIBS)
RuntimePathHelpers.register_package_alias(
    "shared_libs",
    RUNTIME_CONFIG.PATH_SHARED_LIBS,
)

__all__ = ["RUNTIME_CONFIG"]

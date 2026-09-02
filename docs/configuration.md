# Configuration reference

Every DocForge service is configured through environment variables, loaded from per-service files
under `services/<service>/`. Each has a committed `.env.example` template — copy it to `.env` (which is
git-ignored) and adjust:

```bash
cp services/docforge/.env.example         services/docforge/.env
cp services/docforge/postgres.env.example  services/docforge/postgres.env
cp services/docforge/s3_config.json.example services/docforge/s3_config.json
cp services/bge_server/.env.example              services/bge_server/.env
cp services/mcp/.env.example                     services/mcp/.env   # only if you run the MCP server
```

> ⚠️ The template values are **local-dev defaults**. Change every password/secret/token before any
> deployment beyond your machine — see [deployment.md](deployment.md) and [PROD-HARDENING.md](PROD-HARDENING.md).

> **ML providers (embed / rerank / OCR / VLM / LLM) are NOT configured via env.** Their `base_url`, API
> key and model live **per collection** in the database (each collection's pipeline config). To use
> OpenAI / Mistral / Cohere / a local host, set it on the collection, not here.

---

## `services/docforge/.env` — API + worker

The app and worker share this file. In the containerised stack (`--profile full`), compose overrides
`POSTGRES_DSN` / `REDIS_URL` / `QDRANT_URL` / `S3_ENDPOINT_URL` with in-network hostnames, so leave those
at their `localhost` values here (they're used when running the app straight from `uv run` on the host).

> **`DOCFORGE_TAG`** is a **compose-interpolation** variable, not an app/worker knob: docker-compose reads
> it from your shell or a project-root `.env` to select the `ghcr.io/…-<svc>:${DOCFORGE_TAG:-latest}` image
> tag. It is NOT injected into the containers by default. The worker *will* read `DOCFORGE_TAG` (to stamp
> exported bundle provenance, falling back to `unknown` when unset) if you add it to this env file — but
> that is optional and unrelated to image selection.

### FastAPI

| Variable | Default | Notes |
|---|---|---|
| `FASTAPI_APP_NAME` | `DocForge` | Required (no default in config). |
| `FASTAPI_APP_VERSION` | `0.2.0` | Required (no default in config). Surfaced in OpenAPI docs + `/health`. |
| `FASTAPI_DEBUG_MODE` | `false` | **Must be `false` in prod** — `true` leaks full tracebacks to clients. |
| `FASTAPI_CORS_ALLOWED_ORIGINS` | `http://localhost:10046,http://localhost:10040` | Comma-separated. |

### Authentication (API-key bearer)

| Variable | Default | Notes |
|---|---|---|
| `AUTH_ENABLED` | `false` | **Off by default** — dev + the unit suite run unauthenticated. Set `true` to gate every `/api/v1/*` route (Scalar docs + `/openapi.json` stay public). |
| `AUTH_ROOT_TOKEN` | `df_dev_root_token_change_me` | Provisioned at startup as the root user's full-access key. **Use a strong value** and rotate it. Required when `AUTH_ENABLED=true`. |

### Rate limiting (app-only)

| Variable | Default | Notes |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `false` | **Off by default** — nothing is throttled out-of-box. Set `true` in prod. Limits `/api/v1/*` except the high-frequency job-poll/SSE routes, `/health`, `/metrics`, docs and static (so the UI is never throttled). |
| `RATE_LIMIT_PER_MINUTE` | `600` | Per-caller rolling-minute budget. Keyed by API-key identity when auth is on, else by client IP. |
| `RATE_LIMIT_TRUST_FORWARDED_FOR` | `true` | Key IP-based limiting on the proxy-set `X-Forwarded-For`. Set `false` on a **direct-exposed** deployment where XFF is client-forgeable. In-process counter — the limit is **per app instance**; run multiple replicas → use a shared store (not shipped). |

### Metrics (app-only)

| Variable | Default | Notes |
|---|---|---|
| `METRICS_ENABLED` | `true` | Exposes `GET /metrics` (Prometheus text; app + job-queue gauges). **Unauthenticated** — network-restrict it (see PROD-HARDENING §10). Set `false` to disable. Not in the OpenAPI document. |
| `METRICS_SCRAPE_TIMEOUT_SECONDS` | `5.0` | Bounds the infra-gauge refresh (queue depth / job counts / live workers) per scrape. |

### Logging (all five required)

| Variable | Default | Notes |
|---|---|---|
| `LOGGING_CONSOLE_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`. |
| `LOGGING_FILE_LEVEL` | `DEBUG` | Level for file logs (when enabled). |
| `LOGGING_ENABLE_CONSOLE` | `true` | |
| `LOGGING_ENABLE_FILE` | `false` | Rotating file logs. |
| `LOGGING_LPP_FORMAT` | `ShortFormat` | `ShortFormat` \| `DebugFormat`. |

### Data stores

| Variable | Default (dev) | Notes |
|---|---|---|
| `REDIS_URL` | `redis://localhost:10042/0` | arq queue. |
| `POSTGRES_DSN` | `postgresql+asyncpg://docforge:change_me@localhost:10041/docforge` | Async DSN. Credentials **must match** `postgres.env`. |
| `QDRANT_URL` | `http://localhost:10043` | |
| `QDRANT_API_KEY` | *(unset)* | Optional — unset for the local unauthenticated Qdrant. |
| `S3_ENDPOINT_URL` | `http://localhost:10044` | SeaweedFS (S3-compatible). |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | `docforge` / `change_me_s3_secret` | Any non-empty creds work against the local anonymous SeaweedFS. |
| `S3_BUCKET` | `docforge-objects` | Created at startup if missing. |
| `S3_REGION` | `us-east-1` | |
| `QDRANT_TIMEOUT_SECONDS` | `60.0` | Per-request Qdrant timeout (the client's own 5s default is too low for heavy `wait=true` upserts). Read by both app and worker. |

### Search & live streams (app-only)

| Variable | Default | Notes |
|---|---|---|
| `SEARCH_RUN_TIMEOUT_SECONDS` | `30.0` | Wall-clock cap for one inline search run. Guards a stuck/cold provider (a cold CPU embedder's first encode can breach a tight cap → 422). Raise on a slow/contended deployment. |
| `SSE_POLL_INTERVAL_SECONDS` | `0.75` | Poll cadence for the live job SSE stream (poll-backed, no message bus). |

### Document grid & jobs list (app-only)

| Variable | Default | Notes |
|---|---|---|
| `CORPUS_MAX_PAGE_SIZE` | `500` | Hard ceiling for one document-grid query page; a larger requested `limit` is clamped down to this. |
| `CORPUS_MAX_REINGEST_FANOUT` | `1000` | Per-call cap on a bulk re-ingest fan-out: a selector matching more enqueues only the first N (deterministic order) and reports `capped=true` + total `matched`. |
| `JOBS_MAX_PAGE_SIZE` | `500` | Hard ceiling for one `GET /jobs` page (also the default); a larger requested `limit` is clamped down to this. |

### Worker

| Variable | Default | Notes |
|---|---|---|
| `WORKER_CONCURRENCY` | `2` | Concurrent ingestion jobs. |
| `WORKER_JOB_TIMEOUT_SECONDS` | `1800.0` | Global default per-run engine budget (seconds). Must be `<= WORKER_JOB_TIMEOUT_MAX_SECONDS` or the worker refuses to boot. |
| `WORKER_JOB_TIMEOUT_MAX_SECONDS` | `7200.0` | Hard ceiling any single run may request: a per-collection `job_timeout_seconds` is honoured up to this and **rejected** (fail-fast) above it. arq's outer cap derives from this value. |
| `WORKER_JOB_TIMEOUT_GRACE_SECONDS` | `60.0` | Grace added on top of the MAX budget to derive arq's outer per-job cap, so the engine's budget always fires first and arq only kills a genuinely wedged run. |
| `WORKER_HEAVY_THREADS` | `4` | Bounded thread pool for the heavy CPU stages (docling/ocr/render/chunk) dispatched via `asyncio.to_thread`. |
| `WORKER_PREFLIGHT_ENABLED` | `true` | Provider-reachability preflight (fail-fast before spend). Safe on by default: the stock pipeline ships its provider-hosted stages (enrich/metagen) OFF, so only real in-stack nodes are probed; a stage you opt in is preflighted before its first spend. Set `false` to skip reachability checks. |
| `WORKER_NAME` | *(empty → hostname)* | Friendly display name for this worker in the fleet view (`GET /jobs/workers/live`). Set per replica (e.g. `gpu-box-1`) when running several. |

### Worker liveness & stuck-job reaper

| Variable | Default | Notes |
|---|---|---|
| `WORKER_HEARTBEAT_INTERVAL_SECONDS` | `10` | Heartbeat tick interval. Kept well below `WORKER_ALIVE_THRESHOLD_SECONDS`. |
| `WORKER_ALIVE_THRESHOLD_SECONDS` | `30` | A heartbeat fresher than this reads as `alive` (app-side). Must stay `>>` the heartbeat interval (three-missed-ticks rule). |
| `WORKER_PRUNE_STALE_SECONDS` | `180` | A heartbeat frozen past this is pruned (worker deleted + dropped from the fleet view). Read by **both** app and worker (same env → consistent "off" window). Keep well above the alive threshold. |
| `WORKER_HEALTH_CHECK_INTERVAL_SECONDS` | `30` | arq writes a health record to Redis every N seconds; `arq … --check` reads it for the container healthcheck. |
| `WORKER_REAP_ENABLED` | `true` | Stuck-job reaper cron: fails RUNNING jobs idle past the stale cutoff and releases their document to FAILED. Set `false` to skip the reaper (cron not registered). |
| `WORKER_REAP_STALE_SECONDS` | `1200` | A RUNNING job idle longer than this is reaped. **Must be `>= 60`** (the worker refuses to boot below that). 1200s (20m) sits above the slowest observed single-doc run. |
| `WORKER_REAP_INTERVAL_MINUTES` | `5` | Reaper cron cadence (runs on every Nth minute of the hour; also once at startup). |

### Collection export / import (portable `.dcexport` bundles)

| Variable | Default | Notes |
|---|---|---|
| `IMPORT_STAGING_PREFIX` | `collection-imports` | S3 key prefix an uploaded import bundle is staged under before the worker consumes it (app-side). |
| `IMPORT_MAX_BUNDLE_BYTES` | `5368709120` (5 GiB) | Hard ceiling on an uploaded import bundle; the spool aborts with a 413 past this and stages nothing (app-side). |
| `EXPORT_BUNDLE_PREFIX` | `collection-exports` | S3 key prefix a produced export bundle is published under (worker-side). |
| `EXPORT_COMPRESSION` | `zstd` | Bundle compression codec: `zstd` or `none` (worker-side). |
| `EXPORT_TTL_SECONDS` | `604800` (7 days) | How long an exported bundle is retained before it may be GC'd (worker-side). |
| `WORKER_TRANSFER_GC_ENABLED` | `true` | Reclaim expired export bundles (S3 object + `collection_transfer` row) on a cron. Set `false` to skip the sweep (cron not registered). |
| `WORKER_TRANSFER_GC_INTERVAL_MINUTES` | `15` | Transfer-GC cron cadence (runs on every Nth minute of the hour; also once at startup). |

### `postgres.env` and `s3_config.json`

`postgres.env` holds `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` for the Postgres container —
the password **must match** the one in `POSTGRES_DSN`. `s3_config.json` is the SeaweedFS S3 identity
(placeholder locally). Both have `.example` templates.

---

## `services/bge_server/.env` — embedding & rerank host

All variables have safe defaults; the service starts with no `.env` at all.

> **Build variant** is chosen at **image build time**, not via `.env`: `docker compose build bge_server`
> (CPU, ~2 GB) or `docker compose build --build-arg TORCH_VARIANT=gpu bge_server` (CUDA 12.4, ~9.5 GB).
> Set `BGE_DEVICE=cuda` when using the GPU image.

| Variable | Default | Notes |
|---|---|---|
| `BGE_M3_MODEL` | `BAAI/bge-m3` | Dense + sparse embedding model. |
| `BGE_RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | Cross-encoder reranker. |
| `BGE_M3_REVISION` / `BGE_RERANKER_REVISION` | *(pinned SHAs)* | Pin each model to an exact HF commit (supply-chain control) via `snapshot_download`. Set empty to float on `main`. |
| `BGE_DEVICE` | `auto` | `auto` (GPU if present, else CPU) \| `cuda` (require GPU, fail loud) \| `cpu`. |
| `BGE_FP16` | `false` | Gated to CUDA — forced off on CPU with a warning. |
| `BGE_M3_MAX_LENGTH` | `8192` | Max token length for encode. |
| `BGE_MAX_BATCH_SIZE` | `32` | Dynamic-batching: max units per model call. |
| `BGE_MAX_WAIT_MS` | `10` | Batch-formation window (ms); `0` = dispatch immediately. |
| `BGE_TORCH_NUM_THREADS` | `0` | `0` = auto, derived from the container's cgroup CPU quota. |
| `LOGGING_*` | see file | Same logging knobs as above. |

---

## `services/mcp/.env` — MCP server

A pure HTTP client of the DocForge API — no DB/S3 secrets.

| Variable | Default (code) | Notes |
|---|---|---|
| `DOCFORGE_API_URL` | `http://localhost:8000` | The DocForge API the MCP talks to. The shipped `.env.example` sets the in-network service name `http://docforge_app:8000` for the compose service. |
| `MCP_API_TIMEOUT_S` | `60` | Outbound request timeout. |
| `MCP_TRANSPORT` | `stdio` | `stdio` (local Claude Desktop/Code) \| `streamable-http` (container service). The shipped `.env.example` sets `streamable-http` for the compose service. |
| `MCP_HOST` / `MCP_PORT` / `MCP_HTTP_PATH` | `0.0.0.0` / `9000` / `/mcp` | HTTP transport binding (`MCP_PORT` is the container-internal port, published on host `10048`). |
| `DOCFORGE_API_TOKEN` | *(unset)* | **stdio-only fallback.** Outbound bearer used only when running over stdio (no `Authorization` header exists there to forward). In `streamable-http` mode it is never used to serve a request — every incoming request MUST carry its own `Authorization: Bearer <docforge-api-key>`, or the MCP refuses it with 401. Never set this to `AUTH_ROOT_TOKEN` (or any root key) for a networked deployment. Auto-masked in logs. |

> **Access control.** The MCP has no auth of its own — it forwards each caller's own DocForge API
> key upstream, so a caller gets exactly that key's scope. An HTTP request with no bearer is
> refused (401); it never falls back to a shared/local token. See [mcp.md](mcp.md#access-control).

See the [MCP guide](mcp.md) for running and connecting a client.

---

## `services/paddle_server/.env` — PP-StructureV3 layout-parsing sidecar

An optional escalation-parser micro-service (mirrors `bge_server`): a pure PaddleX model host with no
DB/S3 secrets. All variables have safe defaults — it starts with no `.env` at all. It is reached in-network
at `http://paddle_server:80` (dev host port `10049`) and is only exercised when a collection's parse stage
selects the `pp_structure` brick. See [architecture.md](architecture.md) and
[deployment-resources.md](deployment-resources.md) for the parser role and resource footprint.

> **Build variant** is chosen at **image build time**, not via `.env`: `docker compose build paddle_server`
> (CPU, ~2.3 GB) or `docker compose build --build-arg TORCH_VARIANT=gpu paddle_server` (CUDA 12.6, ~4–5.5 GB).

| Variable | Default | Notes |
|---|---|---|
| `PADDLE_PDX_CACHE_HOME` | `/models` | Directory PaddleX caches every downloaded inference model under (`official_models/` subdir). Mounted as a named volume so weights persist. |
| `PADDLE_PDX_MODEL_SOURCE` | `huggingface` | Model hoster: `huggingface` \| `bos` \| `aistudio` \| `modelscope`. |
| `PADDLE_USE_TABLE_RECOGNITION` | `true` | Optional table-recognition sub-pipeline. |
| `PADDLE_USE_FORMULA_RECOGNITION` | `false` | Optional formula-recognition sub-pipeline. |
| `PADDLE_USE_SEAL_RECOGNITION` | `false` | Optional seal-recognition sub-pipeline. |
| `PADDLE_USE_DOC_ORIENTATION_CLASSIFY` | `false` | Optional document-orientation classification. |
| `PADDLE_USE_DOC_UNWARPING` | `false` | Kept off (mapper provenance contract); exposed only so a deployment can flip it back on deliberately. |
| `PADDLE_LOCK_WAIT_TIMEOUT_SECONDS` | `290` | Max seconds a `/layout-parsing` request waits for the shared predict lock before the router returns HTTP 503 (PaddlePaddle inference is not thread-safe). Must be `> 0`. |
| `LOGGING_*` | see file | Same five logging knobs as above (all default: `INFO`/`DEBUG`/`true`/`false`/`ShortFormat`). |

---

## Ports (dev)

| Service | Host port |
|---|---|
| API (`docforge_app`) | `10040` |
| PostgreSQL | `10041` |
| Redis | `10042` |
| Qdrant | `10043` |
| SeaweedFS | `10044` |
| Gotenberg | `10045` |
| Frontend | `10046` |
| bge_server | `10047` |
| MCP | `10048` |
| paddle_server | `10049` |

Production closes the data-plane ports (postgres/redis/qdrant/seaweedfs) — only the API (and optionally
the MCP) are exposed. See [deployment.md](deployment.md).

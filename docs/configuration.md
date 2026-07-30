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

### FastAPI

| Variable | Default | Notes |
|---|---|---|
| `FASTAPI_APP_NAME` | `DocForge` | Required (no default in config). |
| `FASTAPI_APP_VERSION` | `0.1.0` | Required. |
| `FASTAPI_DEBUG_MODE` | `false` | **Must be `false` in prod** — `true` leaks full tracebacks to clients. |
| `FASTAPI_CORS_ALLOWED_ORIGINS` | `http://localhost:10046,http://localhost:10040` | Comma-separated. |

### Authentication (API-key bearer)

| Variable | Default | Notes |
|---|---|---|
| `AUTH_ENABLED` | `false` | **Off by default** — dev + the unit suite run unauthenticated. Set `true` to gate every `/api/v1/*` route (Scalar docs + `/openapi.json` stay public). |
| `AUTH_ROOT_TOKEN` | `df_dev_root_token_change_me` | Provisioned at startup as the root user's full-access key. **Use a strong value** and rotate it. Required when `AUTH_ENABLED=true`. |

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

### Worker

| Variable | Default | Notes |
|---|---|---|
| `WORKER_CONCURRENCY` | `2` | Concurrent ingestion jobs. |
| `WORKER_JOB_TIMEOUT_SECONDS` | `1800` | Per-job timeout. |
| `WORKER_HEAVY_THREADS` | `4` | Thread pool for heavy CPU stages (docling/ocr/render/chunk). |
| `WORKER_PREFLIGHT_ENABLED` | `false` | Opt-in provider-reachability preflight (fail-fast before spend). Keep `false` with the stock placeholder providers; enable only once every provider a collection uses is real + reachable. |

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

| Variable | Default | Notes |
|---|---|---|
| `DOCFORGE_API_URL` | `http://docforge_app:8000` | The DocForge API the MCP talks to (in-network service name). |
| `MCP_API_TIMEOUT_S` | `60` | Outbound request timeout. |
| `MCP_TRANSPORT` | `streamable-http` | `streamable-http` \| `stdio`. |
| `MCP_HOST` / `MCP_PORT` / `MCP_HTTP_PATH` | `0.0.0.0` / `9000` / `/mcp` | HTTP transport binding. |
| `MCP_AUTH_TOKEN` | *(change me)* | **Required in HTTP mode** — the bearer clients must present. Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. |
| `DOCFORGE_API_TOKEN` | *(unset)* | Outbound bearer to the DocForge API — set when the API has `AUTH_ENABLED=true` (equal to `AUTH_ROOT_TOKEN` or any registered key). Auto-masked in logs. |

See the [MCP guide](mcp.md) for running and connecting a client.

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

Production closes the data-plane ports (postgres/redis/qdrant/seaweedfs) — only the API (and optionally
the MCP) are exposed. See [deployment.md](deployment.md).

# Production hardening — go-live checklist

Run this on a **fresh** production deployment of the `docforge` stack. It covers the
secrets and network posture that must NOT ship with the dev defaults. Items already enforced in
the compose files (data-plane ports unpublished in prod, resource limits, healthchecks) are noted
as "already done — verify only".

> The prod stack is `docker-compose.yml` **alone** (no dev override). The dev override
> `docker-compose.dev.yml` is the only place that re-publishes the data-plane ports.

---

## 1. Secrets — rotate before first boot

All of these ship with dev placeholders. Generate fresh values on the prod host.

### 1a. SeaweedFS S3 identity (`services/docforge/s3_config.json`)
The real file is git-ignored; only `s3_config.json.example` is tracked. On the prod host:

```bash
cp services/docforge/s3_config.json.example services/docforge/s3_config.json
# edit accessKey + secretKey to strong random values
python3 -c "import secrets; print('secret:', secrets.token_urlsafe(32))"
```

Set the **same** secret in `services/docforge/.env`:

```
S3_ACCESS_KEY=<the accessKey you chose>
S3_SECRET_KEY=<the secretKey you chose>
```

> The dev secret (`docforge_dev_secret`) is compromised via git history — never reuse it in prod.

### 1b. Postgres password
Fresh volume (recommended for prod): just set a strong password before the first `up` — Postgres
initialises the DB with it.

```
# services/docforge/postgres.env
POSTGRES_USER=docforge
POSTGRES_PASSWORD=<strong random>
```

Mirror it in the app/worker DSN (`services/docforge/.env`, `POSTGRES_*` / DSN).

Existing volume (password already baked in) — rotate in-place instead:

```bash
docker compose -f docker-compose.yml exec docforge_postgres \
  psql -U docforge -c "ALTER USER docforge PASSWORD '<strong random>';"
# then update postgres.env + .env and recreate app+worker
```

### 1c. Redis password
Add `requirepass` and wire it into the app/worker Redis URL.

```yaml
# docker-compose.yml, docforge_redis
command: ["redis-server", "--requirepass", "${REDIS_PASSWORD}"]
```
```
# .env
REDIS_PASSWORD=<strong random>
REDIS_URL=redis://:<strong random>@docforge_redis:6379/0
```

### 1d. Qdrant API key
The app already reads `QDRANT_API_KEY` as optional — set it and pass it to Qdrant.

```yaml
# docker-compose.yml, docforge_qdrant
environment:
  QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY}
```
```
# .env
QDRANT_API_KEY=<strong random>
```

---

## 2. Authentication — turn it on with a real root token

```
# services/docforge/.env
AUTH_ENABLED=true
AUTH_ROOT_TOKEN=df_root_<strong random>   # python3 -c "import secrets; print('df_root_'+secrets.token_urlsafe(32))"
```

`RUNTIME_CONFIG.validate()` fails the boot if `AUTH_ENABLED=true` with an empty `AUTH_ROOT_TOKEN`
(prevents the lockout footgun). The startup bootstrap provisions the root user + key idempotently.
The MCP (if/when deployed) uses this same token as `DOCFORGE_API_TOKEN`.

---

## 3. Debug + CORS

```
FASTAPI_DEBUG_MODE=false                               # true leaks full tracebacks to clients
FASTAPI_CORS_ALLOWED_ORIGINS=https://<your real UI origin>   # never "*" with auth on
```

---

## 4. Network posture — verify (already enforced in prod compose)

- Data-plane ports (postgres 10041, redis 10042, qdrant 10043, seaweedfs 10044, bge 10047) are
  **not** published by `docker-compose.yml` — operator access is via `docker compose exec`.
  Confirm nothing re-publishes them:
  ```bash
  docker compose -f docker-compose.yml --profile full config | grep -E "10041|10042|10043|10044|10047" || echo "clean"
  ```
- Only the API (10040) and Gotenberg (10045) are published. Restrict even these at the OS firewall
  to trusted sources if the VM is reachable from an untrusted network.

---

## 5. Container users (deferred hardening)

The runtime images currently run as root. Before a security-sensitive deployment, add a non-root
`USER` to `app/Dockerfile`, `worker/Dockerfile`, `bge_server/Dockerfile`, ensuring the HF model
cache (`/models`) and any writable dirs are chown'd to that user on first mount. Left as a
follow-up because it requires an image rebuild + volume-ownership validation.

---

## 6. Worker resilience — heavy-stage isolation + the hung-call residual

The pipeline's blocking stages (docling parse, RapidOCR, figure render, chunk tokenizer) run on a
**bounded** thread pool (`WORKER_HEAVY_THREADS`, default 4) instead of asyncio's unbounded default
executor. This caps concurrent native work (a ForEach fan-out can't spawn dozens of docling/OCR
threads and oversubscribe CPU/memory) and bounds how many threads a hung native call can leak.

**Known residual (by design, not a silent failure):** a wall-clock run timeout cancels the awaiting
coroutine but **cannot kill an in-flight native call** — Python threads are not cancellable. A truly
hung docling/OCR call therefore holds one heavy-pool thread until the worker process restarts;
enough simultaneous hangs (≥ `WORKER_HEAVY_THREADS`) stall new heavy work on that worker. The
per-run timeout still marks such a job **failed** (never silently succeeded).

**Garde-fou:** the worker writes an arq health record every 30s; its container healthcheck
(`arq entrypoint.WorkerSettings --check`) turns the container **unhealthy** when the worker stops
making progress. Docker does **not** auto-restart on unhealthy — to close the loop, add an autoheal
sidecar (trade-off: it needs the Docker socket) or restart the worker manually when it goes
unhealthy:

```yaml
# docker-compose.yml (optional) — restarts any container that reports unhealthy
  autoheal:
    image: willfarrell/autoheal:1.2.0
    environment: { AUTOHEAL_CONTAINER_LABEL: all }
    volumes: [ "/var/run/docker.sock:/var/run/docker.sock" ]
    restart: unless-stopped
```

The fully-correct alternative (run each job in a killable subprocess) was deliberately not taken:
at `WORKER_CONCURRENCY=2` on a single VM the blast radius is small and a subprocess harness adds IPC
+ cold-model-load cost + orphan-process management. Revisit if concurrency rises or you go
multi-worker.

## 7. Provider preflight (opt-in fail-fast before spend)

Every provider node (llm/vlm/ocr-mistral/embed) has a `preflight()` that probes its `base_url`
reachability + credentials AFTER build/validate and BEFORE the first spend — a wrong/unreachable
endpoint or a rejected key then fails the job immediately, having stored nothing (closing the gap the
structural validator can't cover). It is **opt-in** (`WORKER_PREFLIGHT_ENABLED`, default `false`):

- The stock pipeline ships PLACEHOLDER endpoints (`http://llm:8000`, `http://vlm:8000`) that you
  replace per collection, and the sweep probes EVERY provider node — including branches a given
  document never reaches (the figure VLM on a text-only PDF). On-by-default would fail ingestions on
  un-configured placeholders.
- Enable it (`WORKER_PREFLIGHT_ENABLED=true` + recreate the worker) only once **every** provider your
  collections reference is real and reachable. Then a typo'd `base_url` or a bad key fails the upload's
  job fast with a clear per-node message instead of mid-run after spend.

## 8. Final pre-flight

```bash
# both configs still resolve
docker compose -f docker-compose.yml --profile full config >/dev/null && echo "prod config OK"
# migrations applied
docker compose -f docker-compose.yml exec docforge_app sh -c 'alembic -c /app/shared/alembic.ini upgrade head'
# health
curl -fsS http://localhost:10040/health && echo " API healthy"
```

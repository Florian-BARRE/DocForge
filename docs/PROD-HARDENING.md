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
The MCP (if/when deployed) does NOT need this token: `DOCFORGE_API_TOKEN` in `services/mcp/.env` is
only its stdio-local fallback and should be a separate, non-root, narrowly-scoped key — see
[§4](#4-network-posture--verify-already-enforced-in-prod-compose) and
[mcp.md#access-control](mcp.md#access-control).

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
- **MCP port 10048 IS published by `docker-compose.yml`** (`docforge_mcp`, `profiles: ["full"]`)
  whenever the MCP is deployed. It has no auth of its own: every request must carry
  `Authorization: Bearer <docforge-api-key>` (a caller's own DocForge API key), forwarded upstream
  as-is; a request without one is refused with 401 — it never falls back to a shared/local token
  (`DOCFORGE_API_TOKEN` is a stdio-only fallback, unreachable from this port). Front 10048 with TLS
  on an untrusted network, restrict it at the OS firewall the same as 10040, and set
  `services/mcp/.env`'s `DOCFORGE_API_TOKEN` to a non-root, narrowly-scoped key (or leave it empty)
  — never `AUTH_ROOT_TOKEN`. Full model: [mcp.md#access-control](mcp.md#access-control).

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

## 7. Provider preflight (fail-fast before spend, on by default)

Every provider node (llm/vlm/ocr-mistral/embed) has a `preflight()` that probes its `base_url`
reachability + credentials AFTER build/validate and BEFORE the first spend — a wrong/unreachable
endpoint or a rejected key then fails the job immediately, having stored nothing (closing the gap the
structural validator can't cover). It is **on by default** (`WORKER_PREFLIGHT_ENABLED=true`):

- The stock pipeline ships its provider-hosted stages (figure ENRICH via VLM, chunk/document METAGEN
  via LLM) **OFF** — their recommended endpoints are pre-filled but not in any executed graph until
  you opt in. So out-of-box the sweep only probes real, reachable in-stack nodes (gotenberg `/health`,
  bge_server); no placeholder is ever hit.
- When you opt a provider stage in, set its endpoint and the preflight probes it before the first
  spend — a typo'd `base_url` or a bad key then fails the upload's job fast with a clear per-node
  message instead of mid-run after spend. Note the sweep probes EVERY provider node in the graph,
  including branches a given document never reaches (the figure VLM on a text-only PDF), so every
  enabled provider must be real and reachable.
- Set `WORKER_PREFLIGHT_ENABLED=false` (+ recreate the worker) only to skip reachability checks
  entirely — e.g. to defer a not-yet-configured provider to run-time failure instead of preflight.

## 8. Optional TLS reverse proxy

DocForge does **not** terminate TLS by default — `docker-compose.yml` publishes the API in plain
HTTP (port 10040) on the assumption that something in front of it already handles TLS.

**When NOT to use this section:** if the host/VM, a corporate load balancer, or a platform ingress
already terminates TLS in front of DocForge, leave the base compose alone. DocForge stays on plain
HTTP behind that proxy — just make sure the operator's proxy:
- forwards `X-Forwarded-For` with the real client IP (the app's rate-limiter keys on it — see
  [§9](#9-rate-limiting) below), and
- enables the app-level rate limit, since there is no edge limiter of DocForge's own in this case.

**When to use it:** a bare host with a public IP and nothing else terminating TLS. Layer the optional
`docker-compose.proxy.yml` overlay — a Caddy 2 front door with automatic HTTPS (Let's Encrypt):

```bash
# project-root .env (compose interpolation, same mechanism as DOCFORGE_TAG):
DOCFORGE_DOMAIN=docforge.example.com     # A/AAAA record must already point at this host
DOCFORGE_ACME_EMAIL=ops@example.com      # Let's Encrypt expiry/revocation contact

docker compose -f docker-compose.yml -f docker-compose.proxy.yml --profile full up -d
```

What it changes:
- Adds `docforge_caddy`, publishing **80/443** (80 = ACME HTTP-01 challenge + auto HTTP→HTTPS
  redirect, 443 = the public entry point, TCP and UDP/QUIC).
- `docforge_app` **stops publishing 10040**: once this overlay is used, 443 on `docforge_caddy` is
  the only public entry point, so plaintext API access can no longer bypass TLS. Internal/operator
  access still works via `docker compose exec docforge_app ...`.
- Caddy's `reverse_proxy` **sets** (not appends) `X-Forwarded-For` to the actual connecting peer and
  `X-Forwarded-Proto`/`X-Forwarded-Host` accordingly (`services/caddy/Caddyfile`) — any
  client-supplied `X-Forwarded-For` is discarded rather than trusted, so the app's rate-limiter can
  key on it safely without needing to parse "last hop only" out of an appendable header.
- ACME account + certs persist in the `docforge_caddy_data` volume — they are **not** re-fetched on
  every `docker compose up`, which would otherwise risk Let's Encrypt's rate limits.

Edge rate-limiting is intentionally not added to Caddy — the app's own rate limit
([§9](#9-rate-limiting)) is keyed on the `X-Forwarded-For` Caddy sets above, and a real Caddy rate
limiter needs a custom `xcaddy` build, which is more machinery than a TLS-only front door needs.

## 9. Rate limiting

Enable the app's own rate limit in `services/docforge/.env`, then recreate `docforge_app`:
- `RATE_LIMIT_ENABLED` (default `false`) — off out-of-box so nothing breaks; set `true` in prod.
- `RATE_LIMIT_PER_MINUTE` (default `600`) — per-caller rolling-minute budget.
- `RATE_LIMIT_TRUST_FORWARDED_FOR` (default `true`) — key IP-based limiting on the proxy-set
  `X-Forwarded-For`; set `false` on a direct-exposed deployment where XFF is client-forgeable.

When auth is on, the limiter keys by API-key identity (XFF is ignored); when auth is off, it keys by
client IP. The high-frequency job-poll/SSE routes, `/health`, `/metrics`, docs and static assets are
exempt, so the UI is never throttled. It keys on `X-Forwarded-For`, so:
- **Behind `docker-compose.proxy.yml`:** already correct out of the box — Caddy authoritatively sets
  that header (see [§8](#8-optional-tls-reverse-proxy)).
- **Behind your own TLS-terminating proxy/LB:** you must configure it to forward
  `X-Forwarded-For` with the real client IP yourself, or every request will appear to come from the
  proxy's own IP and share one limiter bucket.
- **No proxy at all (direct to 10040):** `X-Forwarded-For` is client-supplied and trivially spoofable
  — do not rely on it for anything beyond coarse abuse mitigation in that topology.

## 10. Metrics scraping

DocForge exposes app + job-queue metrics at `/metrics` (Prometheus exposition format) on the API
service. Knobs (`services/docforge/.env`): `METRICS_ENABLED` (default `true`; set `false` to disable
the endpoint entirely) and `METRICS_SCRAPE_TIMEOUT_SECONDS` (default `5.0`; bounds the infra-gauge
refresh per scrape). The endpoint is **unauthenticated** — never expose it publicly:
- Behind `docker-compose.proxy.yml`, do not route it through Caddy's public site block; scrape it
  over `docforge_net` directly (`http://docforge_app:8000/metrics`) from a Prometheus that also lives
  on that network, or restrict it at the OS firewall if scraping from outside the Docker network.
- DocForge does **not** ship a bundled Prometheus/Grafana stack. A minimal external scrape config:
  ```yaml
  scrape_configs:
    - job_name: docforge
      static_configs:
        - targets: ["docforge_app:8000"]   # or host:10040 if you still publish it directly
  ```
- **Container CPU/RAM/GPU are out of scope for this endpoint** — DocForge exposes application-level
  metrics only (jobs, queue depth, request latency, etc.), never host/container resource usage. Get
  those from your own `cAdvisor` / `node-exporter` / `dcgm-exporter` deployment, independent of
  DocForge.

## 11. Log aggregation

DocForge does not run its own ELK/Loki stack — the app/worker log to **stdout** (via
`loggerplusplus`, see `LOGGING_CONSOLE_LEVEL` / `LOGGING_LPP_FORMAT` in
[configuration.md](configuration.md)), exactly what Docker's own logging drivers are built to collect.
Point the **Docker logging driver** at your external collector instead of adding one to the stack.

Per-service, in whichever compose file you layer last (or a small local override you keep out of git):
```yaml
services:
  docforge_app:
    logging:
      driver: loki                # or fluentd, gelf, syslog, journald, awslogs, ...
      options:
        loki-url: "https://loki.example.com:3100/loki/api/v1/push"
```
Or globally for the whole Docker host, in `/etc/docker/daemon.json` (applies to every container,
requires `dockerd` restart):
```json
{
  "log-driver": "fluentd",
  "log-opts": { "fluentd-address": "fluentd.example.com:24224" }
}
```
The `json-file` default (unbounded by default — pair with `max-size`/`max-file` options if you keep
it) works fine for a single VM without external aggregation; switch drivers only when you have a
collector to point at.

## 12. Final pre-flight

```bash
# both configs still resolve
docker compose -f docker-compose.yml --profile full config >/dev/null && echo "prod config OK"
# migrations applied
docker compose -f docker-compose.yml exec docforge_app sh -c 'alembic -c /app/shared/alembic.ini upgrade head'
# health
curl -fsS http://localhost:10040/health && echo " API healthy"
```

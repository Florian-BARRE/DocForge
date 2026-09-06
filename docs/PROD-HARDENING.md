# Production hardening — go-live checklist

Run this on a **fresh** production deployment of the `docforge` stack. It covers the
secrets and network posture that must NOT ship with the dev defaults. Items already enforced in
the compose files (data-plane ports unpublished in prod, resource limits, healthchecks) are noted
as "already done — verify only".

> The prod stack is `compose/compose.prod-cpu.yml` (or `compose/compose.prod-gpu.yml` on a GPU host) — the
> repo-root `docker-compose.yml` is a thin `include:` of `compose/compose.prod-cpu.yml`, so the two are
> equivalent. The dev overlay `compose/overlays/compose.dev.yml` (only reachable via `compose/compose.dev-cpu.yml`
> / `compose/compose.dev-gpu.yml`) is the only place that re-publishes the data-plane ports. See
> [compose/README.md](../compose/README.md) for the full scenario/add-on matrix.

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
docker compose exec docforge_postgres \
  psql -U docforge -c "ALTER USER docforge PASSWORD '<strong random>';"
# then update postgres.env + .env and recreate app+worker
```

### 1c. Redis password
Add `requirepass` and wire it into the app/worker Redis URL.

```yaml
# compose/compose.base.yml, docforge_redis
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
# compose/compose.base.yml, docforge_qdrant
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
  **not** published by `compose/compose.prod-cpu.yml` / `compose/compose.prod-gpu.yml` — operator access is via
  `docker compose exec`. Confirm nothing re-publishes them:
  ```bash
  docker compose -f compose/compose.prod-cpu.yml --profile full config | grep -E "10041|10042|10043|10044|10047" || echo "clean"
  ```
- Only the API (10040) and Gotenberg (10045) are published. Restrict even these at the OS firewall
  to trusted sources if the VM is reachable from an untrusted network.
- **MCP port 10048 IS published by the prod compose** (`docforge_mcp`, `profiles: ["full"]`)
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
# compose/compose.base.yml (optional) — restarts any container that reports unhealthy
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

### Provider egress allowlist (SSRF, optional — OFF by default)

A provider `base_url` is **per-collection and writable by any WRITE-scoped key**. Two consequences on
an untrusted-tenant deployment: the READ-scoped `GET /collections/{id}/health` sweep, which reports each
endpoint's reachability, doubles as an authenticated **port/host scanner** of the internal Docker
network; and at run time the llm/vlm/ocr/embed nodes POST to that URL. `PROVIDER_EGRESS_ALLOWLIST`
(empty = **OFF, the default** — behaviour unchanged, so the in-stack `gotenberg`/`bge_server`/
`paddle_server` hostnames keep working) is a comma-separated allowlist of host globs and/or IP/CIDR
entries. When set, it is enforced at two edges:

- **The health sweep** — an endpoint whose host is not allowed is reported `blocked` and **never
  probed**, so the endpoint stops being a scanner.
- **Worker preflight** — a disallowed provider is refused before the first spend, so an enabled but
  off-allowlist provider fails the job fast with a clear per-node message.

Honest scope: the **runtime** in-node POSTs (during a run) are NOT blocked per-call — pipeline nodes
read no config by design. They rely on the allowlist being enforced at preflight (which gates before
any spend) **plus** network-level egress control (a firewall / egress proxy on the worker). For a
multi-tenant deployment where tenants supply their own `base_url`, set both `PROVIDER_EGRESS_ALLOWLIST`
(to the endpoints you actually use) **and** a network egress policy; a single-tenant/trusted-operator
deployment can leave it OFF. Set the **same value** on the app and the worker.

## 8. Optional TLS reverse proxy

DocForge does **not** terminate TLS by default — the prod compose publishes the API in plain
HTTP (port 10040) on the assumption that something in front of it already handles TLS.

**When NOT to use this section:** if the host/VM, a corporate load balancer, or a platform ingress
already terminates TLS in front of DocForge, leave the base compose alone. DocForge stays on plain
HTTP behind that proxy — just make sure the operator's proxy:
- forwards `X-Forwarded-For` with the real client IP (the app's rate-limiter keys on it — see
  [§9](#9-rate-limiting) below), and
- enables the app-level rate limit, since there is no edge limiter of DocForge's own in this case.

**When to use it:** a bare host with a public IP and nothing else terminating TLS. Layer the
optional `compose/overlays/compose.proxy.yml` add-on on top of any scenario file — a Caddy 2 front door
with automatic HTTPS (Let's Encrypt):

```bash
# project-root .env (compose interpolation, same mechanism as DOCFORGE_TAG):
DOCFORGE_DOMAIN=docforge.example.com     # A/AAAA record must already point at this host
DOCFORGE_ACME_EMAIL=ops@example.com      # Let's Encrypt expiry/revocation contact

docker compose -f compose/compose.prod-cpu.yml -f compose/overlays/compose.proxy.yml --profile full up -d
# or: make up-prod-cpu-proxy  (see compose/README.md for every scenario × proxy combo)
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
- `RATE_LIMIT_TRUST_FORWARDED_FOR` (default `false`) — off out-of-box (no proxy → XFF is
  client-forgeable, so the transport peer is keyed); set `true` only behind a proxy that overwrites
  `X-Forwarded-For` (e.g. the Caddy overlay).

Failed-auth traffic is throttled too (when the limiter is on): a request that fails authentication
short-circuits at the auth gate before the limiter proper, so the gate itself throttles those attempts
by client IP (keyed `authfail:<ip>`, honouring `RATE_LIMIT_TRUST_FORWARDED_FOR`) to close the
credential-flood / 401-DoS bypass. Two consequences of the IP keying to be aware of: with
`RATE_LIMIT_TRUST_FORWARDED_FOR=true` a hostile client rotating spoofed `X-Forwarded-For` values
spreads its attempts across per-IP buckets (bounded to distinct values seen within one rolling
minute) — only enable that flag behind a proxy that **overwrites** XFF; and behind an untrusted proxy
(the default) all failed-auth attempts share the proxy's single bucket, so one attacker can push other
clients' already-failing attempts from 401 to 429 (no practical impact — they were failing regardless).

When auth is on, the limiter keys by API-key identity (XFF is ignored); when auth is off, it keys by
client IP. The high-frequency job-poll/SSE routes, `/health`, `/metrics`, docs and static assets are
exempt, so the UI is never throttled (the failed-auth throttle above deliberately does **not** apply
that exemption — a request without valid credentials is never a legitimate poll). It keys on
`X-Forwarded-For`, so:
- **Behind `compose/overlays/compose.proxy.yml`:** already correct out of the box — Caddy authoritatively
  sets that header (see [§8](#8-optional-tls-reverse-proxy)).
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
- Behind `compose/overlays/compose.proxy.yml`, do not route it through Caddy's public site block; scrape it
  over `docforge_net` directly (`http://docforge_app:8000/metrics`) from a Prometheus that also lives
  on that network, or restrict it at the OS firewall if scraping from outside the Docker network.
- DocForge ships an **optional** turnkey Prometheus/Loki/Promtail/Grafana stack —
  `compose/overlays/compose.telemetry.yml`, layered the same way as the proxy add-on:
  ```bash
  docker compose -f compose/compose.prod-cpu.yml -f compose/overlays/compose.telemetry.yml --profile full up -d
  # or: make up-prod-cpu-telemetry
  ```
  It scrapes exactly the target below (in-network, not the published port) and provisions a
  starter dashboard. See [compose/README.md](../compose/README.md#the-telemetry-stack) for the
  ports, the Grafana admin password, and the full config. If you'd rather point your own external
  Prometheus at DocForge instead:
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
# config still resolves
docker compose -f compose/compose.prod-cpu.yml --profile full config >/dev/null && echo "prod config OK"
# migrations applied
docker compose exec docforge_app sh -c 'alembic -c /app/shared/alembic.ini upgrade head'
# health
curl -fsS http://localhost:10040/health && echo " API healthy"
```

---

## 13. Accepted dependency risks

Vulnerabilities we knowingly ship, with the compensating control and the condition that would lift
the acceptance. Re-evaluate on every dependency-hardening pass.

### `transformers` pinned `<5` (worker image)

- **Pin**: `worker` group, `transformers>=4.46,<5` (`src/docforge/pyproject.toml`). The cap is an API-compat
  guard (docling's `AutoProcessor` path breaks on the 5.x API) **and** a deliberate security decision.
- **Open CVEs blocked by staying on 4.x** — all are remote-code-execution / deserialization classes
  triggered **at model load time**: PYSEC-2025-217, PYSEC-2026-2288, PYSEC-2026-2289, PYSEC-2026-2290,
  CVE-2026-9856. None is reachable without loading an attacker-controlled model or config.
- **Compensating control** — the attack surface (untrusted model loading) is not exposed:
  - transformers is a *transitive, worker-only* dependency of docling; DocForge never calls it directly.
  - docling loads only **pinned, first-party model IDs** it bundles/downloads from trusted sources — no
    user-supplied model path or repo id ever reaches `from_pretrained`.
  - **no `trust_remote_code=True`** anywhere (docling defaults it off; DocForge never overrides it), so
    the remote-code execution vectors are inert.
  - the worker is an internal sidecar with no public ingress; it processes documents, not model artifacts.
- **Condition to lift** — when docling declares support for `transformers>=5` (its `AutoProcessor` usage
  is 5.x-compatible), raise the cap to `<6` and re-lock; the CVEs are fixed in the 5.x line.

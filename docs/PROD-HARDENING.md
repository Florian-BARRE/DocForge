# Production hardening — go-live checklist (rework stack)

Run this on a **fresh** production deployment of the `docforge-rework` stack. It covers the
secrets and network posture that must NOT ship with the dev defaults. Items already enforced in
the compose files (data-plane ports unpublished in prod, resource limits, healthchecks) are noted
as "already done — verify only".

> The prod stack is `docker-compose.rework.yml` **alone** (no dev override). The dev override
> `docker-compose.rework.dev.yml` is the only place that re-publishes the data-plane ports.

---

## 1. Secrets — rotate before first boot

All of these ship with dev placeholders. Generate fresh values on the prod host.

### 1a. SeaweedFS S3 identity (`services/docforge-rework/s3_config.json`)
The real file is git-ignored; only `s3_config.json.example` is tracked. On the prod host:

```bash
cp services/docforge-rework/s3_config.json.example services/docforge-rework/s3_config.json
# edit accessKey + secretKey to strong random values
python3 -c "import secrets; print('secret:', secrets.token_urlsafe(32))"
```

Set the **same** secret in `services/docforge-rework/.env`:

```
S3_ACCESS_KEY=<the accessKey you chose>
S3_SECRET_KEY=<the secretKey you chose>
```

> The dev secret (`docforge_dev_secret`) is compromised via git history — never reuse it in prod.

### 1b. Postgres password
Fresh volume (recommended for prod): just set a strong password before the first `up` — Postgres
initialises the DB with it.

```
# services/docforge-rework/postgres.env
POSTGRES_USER=docforge
POSTGRES_PASSWORD=<strong random>
```

Mirror it in the app/worker DSN (`services/docforge-rework/.env`, `POSTGRES_*` / DSN).

Existing volume (password already baked in) — rotate in-place instead:

```bash
docker compose -f docker-compose.rework.yml exec rework_postgres \
  psql -U docforge -c "ALTER USER docforge PASSWORD '<strong random>';"
# then update postgres.env + .env and recreate app+worker
```

### 1c. Redis password
Add `requirepass` and wire it into the app/worker Redis URL.

```yaml
# docker-compose.rework.yml, rework_redis
command: ["redis-server", "--requirepass", "${REDIS_PASSWORD}"]
```
```
# .env
REDIS_PASSWORD=<strong random>
REDIS_URL=redis://:<strong random>@rework_redis:6379/0
```

### 1d. Qdrant API key
The app already reads `QDRANT_API_KEY` as optional — set it and pass it to Qdrant.

```yaml
# docker-compose.rework.yml, rework_qdrant
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
# services/docforge-rework/.env
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
  **not** published by `docker-compose.rework.yml` — operator access is via `docker compose exec`.
  Confirm nothing re-publishes them:
  ```bash
  docker compose -f docker-compose.rework.yml --profile full config | grep -E "10041|10042|10043|10044|10047" || echo "clean"
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

## 6. Final pre-flight

```bash
# both configs still resolve
docker compose -f docker-compose.rework.yml --profile full config >/dev/null && echo "prod config OK"
# migrations applied
docker compose -f docker-compose.rework.yml exec rework_app sh -c 'alembic -c /app/shared/alembic.ini upgrade head'
# health
curl -fsS http://localhost:10040/health && echo " API healthy"
```

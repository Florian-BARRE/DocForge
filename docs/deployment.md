# Deployment

This guide covers running DocForge beyond local dev. For the exhaustive pre-go-live runbook, see
**[PROD-HARDENING.md](PROD-HARDENING.md)**; for sizing/resources see
**[deployment-resources.md](deployment-resources.md)**.

## Production vs dev compose

DocForge ships three compose files:

| File | Role |
|---|---|
| `docker-compose.rework.yml` | The base stack — **this is production**. Baked images, data-plane ports **not** published (postgres/redis/qdrant/seaweedfs stay internal to `rework_net`). |
| `docker-compose.rework.dev.yml` | Dev overlay — hot reload + publishes the store ports to `localhost` for inspection. |
| `docker-compose.rework.gpu.yml` | GPU overlay for docling (worker) acceleration. |

**Production start** (no dev overlay):

```bash
docker compose -f docker-compose.rework.yml --profile full up -d
docker compose -f docker-compose.rework.yml exec rework_app \
  sh -c 'alembic -c /app/shared/alembic.ini upgrade head'
```

`--profile full` is mandatory (app/worker/frontend live under it). Only the API — and optionally the
MCP — should be published to the outside; keep the data-plane services internal.

## Go-live checklist

1. **Secrets.** Replace every placeholder in `services/*/.env`, `postgres.env`, `s3_config.json`:
   - `AUTH_ROOT_TOKEN` (strong, rotated), Postgres password (matched in `POSTGRES_DSN` **and**
     `postgres.env`), S3 access/secret, `MCP_AUTH_TOKEN` (if running the MCP).
   - `POSTGRES_DSN` can also be driven from a shell/`.env` `POSTGRES_DSN` — the compose default is only a
     fallback (`${POSTGRES_DSN:-...}`).
2. **Turn auth ON.** Set `AUTH_ENABLED=true` + a strong `AUTH_ROOT_TOKEN`, then **recreate** the app
   container (a restart does not reload env). The root token is provisioned idempotently at startup as
   the root full-access key; issue narrower, scoped keys for real clients (see the
   [REST](rest-api.md) / [SDK](python-sdk.md) key-management sections). Scalar docs + `/openapi.json`
   stay public by design.
3. **`FASTAPI_DEBUG_MODE=false`** — `true` leaks tracebacks to clients.
4. **CORS** — set `FASTAPI_CORS_ALLOWED_ORIGINS` to your real front-end origins.
5. **Data-plane ports closed** — verify with `docker compose -f docker-compose.rework.yml config` that
   postgres/redis/qdrant/seaweedfs have no `ports:` mapping.
6. **Persistence** — the named volumes (postgres data, Qdrant, SeaweedFS, the `bge_server` HF model
   cache) are where your data lives; back them up.
7. **Provider preflight** — once every provider a collection uses is real and reachable, you may set
   `WORKER_PREFLIGHT_ENABLED=true` to fail fast before spending on an unreachable endpoint.

## GPU

The `bge_server` and the worker's docling stage can use a GPU:

- **`bge_server`**: build the GPU image and set the device policy.
  ```bash
  docker compose -f docker-compose.rework.yml build --build-arg TORCH_VARIANT=gpu bge_server
  # then in services/bge_server/.env:  BGE_DEVICE=cuda   (BGE_FP16=true is gated to CUDA)
  ```
- **Worker docling**: add the GPU overlay:
  `docker compose -f docker-compose.rework.yml -f docker-compose.rework.gpu.yml --profile full up -d`.

A GPU host needs the NVIDIA Container Toolkit. See the commented `reservations:` block under
`bge_server` in the compose file.

## The MCP server (optional)

If you want AI clients to drive DocForge, run the MCP service and expose its port with a strong
`MCP_AUTH_TOKEN`. See the [MCP guide](mcp.md) for transports, ports and connecting a client.

## Upgrades & migrations

Schema changes ship as Alembic migrations. On deploy, run
`alembic -c /app/shared/alembic.ini upgrade head` inside `rework_app` (env.py runs async on asyncpg —
no psycopg2 in the runtime image). Migrations are additive and reviewed for zero-downtime where possible.

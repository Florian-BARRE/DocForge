# Deployment

This guide covers running DocForge beyond local dev. For the exhaustive pre-go-live runbook, see
**[PROD-HARDENING.md](PROD-HARDENING.md)**; for sizing/resources see
**[deployment-resources.md](deployment-resources.md)**.

## Production vs dev compose

DocForge's compose files live under [`compose/`](../compose/README.md) — a base file, overlays,
and four ready-made scenario files, layered via `include:`. The repo-root `docker-compose.yml` is
a thin `include: [compose/compose.prod-cpu.yml]`, so a bare `docker compose --profile full up -d` at the
repo root is still the production default.

| File | Role |
|---|---|
| `compose/compose.base.yml` | ALL services + volumes + network. Never used alone — always via one of the scenario files below. Baked images, data-plane ports **not** published (postgres/redis/qdrant/seaweedfs stay internal to `docforge_net`). |
| `compose/compose.prod-cpu.yml` | **This is production** (the default). `compose.base.yml` alone — CPU is the base variant, no separate CPU overlay exists. |
| `compose/compose.prod-gpu.yml` | Production on a GPU host — `compose.base.yml` + `overlays/compose.gpu.yml`. |
| `compose/compose.dev-cpu.yml` | Local dev — `compose.base.yml` + `overlays/compose.dev.yml` (hot reload + publishes the store ports to `localhost` for inspection). |
| `compose/compose.dev-gpu.yml` | Local dev on a GPU-equipped machine. |
| `compose/overlays/compose.proxy.yml` | **Optional add-on** (layered with an extra `-f`, never baked into a scenario file) — opt-in Caddy TLS front door (auto-HTTPS) for hosts with no proxy/LB already terminating TLS. Off by default; see [PROD-HARDENING.md §8](PROD-HARDENING.md#8-optional-tls-reverse-proxy). |
| `compose/overlays/compose.telemetry.yml` | **Optional add-on** — Prometheus + Loki + Promtail + Grafana. See [compose/README.md](../compose/README.md#the-telemetry-stack). |

See [compose/README.md](../compose/README.md) for the full usage matrix, the Makefile targets,
and the `include:` merge-order gotcha (why overlays are listed *before* `compose.base.yml` in each
scenario file).

**Production start** (no dev overlay):

```bash
docker compose --profile full up -d
docker compose exec docforge_app \
  sh -c 'alembic -c /app/shared/alembic.ini upgrade head'
```

`--profile full` is mandatory (app/worker/frontend live under it). Only the API — and optionally the
MCP — should be published to the outside; keep the data-plane services internal.

## Go-live checklist

1. **Secrets.** Replace every placeholder in `services/*/.env`, `postgres.env`, `s3_config.json`:
   - `AUTH_ROOT_TOKEN` (strong, rotated), Postgres password (matched in `POSTGRES_DSN` **and**
     `postgres.env`), S3 access/secret.
   - If running the MCP, set `services/mcp/.env`'s `DOCFORGE_API_TOKEN` (its stdio-only fallback —
     never the HTTP path) to a **non-root, narrowly-scoped** DocForge API key, or leave it empty.
     There is no `MCP_AUTH_TOKEN` to set: the MCP has no auth of its own, see the
     [MCP guide](mcp.md#access-control).
   - `POSTGRES_DSN` can also be driven from a shell/`.env` `POSTGRES_DSN` — the compose default is only a
     fallback (`${POSTGRES_DSN:-...}`).
2. **Turn auth ON.** Set `AUTH_ENABLED=true` + a strong `AUTH_ROOT_TOKEN`, then **recreate** the app
   container (a restart does not reload env). The root token is provisioned idempotently at startup as
   the root full-access key; issue narrower, scoped keys for real clients (see the
   [REST](rest-api.md) / [SDK](python-sdk.md) key-management sections). Scalar docs + `/openapi.json`
   stay public by design.
3. **`FASTAPI_DEBUG_MODE=false`** — `true` leaks tracebacks to clients.
4. **CORS** — set `FASTAPI_CORS_ALLOWED_ORIGINS` to your real front-end origins.
5. **Data-plane ports closed** — verify with `docker compose -f compose/compose.prod-cpu.yml config` that
   postgres/redis/qdrant/seaweedfs have no `ports:` mapping.
6. **Persistence** — the named volumes (postgres data, Qdrant, SeaweedFS, the `bge_server` HF model
   cache) are where your data lives; back them up.
7. **Provider preflight** — on by default (`WORKER_PREFLIGHT_ENABLED=true`): every provider node is
   probed for reachability before the first spend, so a wrong/unreachable endpoint fails the job fast
   with a clear per-node message. The stock pipeline ships its provider-hosted stages OFF, so only
   real in-stack nodes are probed out-of-box; set `false` to skip the checks entirely.

## GPU

The `bge_server`, `paddle_server`, and the worker's docling stage can use a GPU. Use the
`prod-gpu` scenario — it pulls the published `-gpu` image tags and grants the NVIDIA device to
all three:

```bash
docker compose -f compose/compose.prod-gpu.yml --profile full up -d
# then in services/bge_server/.env:  BGE_DEVICE=cuda   (BGE_FP16=true is gated to CUDA)
```

A GPU host needs the NVIDIA Container Toolkit. See [compose/README.md](../compose/README.md) for
the full scenario matrix, and `compose/overlays/compose.gpu.yml` for the resource `reservations:`.

## The MCP server (optional)

If you want AI clients to drive DocForge, run the MCP service. It has no auth of its own — it is a
pure pass-through that forwards each caller's own `Authorization: Bearer <docforge-api-key>`
upstream, and refuses (401) any request that doesn't carry one. **Port 10048 IS published in this
prod compose**, so front it with TLS on an untrusted network and set its stdio-only
`DOCFORGE_API_TOKEN` fallback to a non-root key (or leave it empty) — never a root/admin key. See
the [MCP guide](mcp.md#access-control) for the full model, transports, ports, and connecting a client.

## Upgrades & migrations

Schema changes ship as Alembic migrations. On deploy, run
`alembic -c /app/shared/alembic.ini upgrade head` inside `docforge_app` (env.py runs async on asyncpg —
no psycopg2 in the runtime image). Migrations are additive and reviewed for zero-downtime where possible.

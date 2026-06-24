# Infra — Memory Index

Containerization & deployment for DocForge. Docker + docker compose (v2) on Windows + Docker Desktop.

## Images (all build from context `src/`)

| Service | Dockerfile | Image | Notes |
|---|---|---|---|
| docforge (API) | `docforge/app/Dockerfile` | `docforge:latest` | light — NO docling; frontend `ui-build` stage |
| worker | `docforge/worker/Dockerfile` | `docforge-worker:latest` | heavy — `--extra worker` = docling |
| bge_server | `bge_server/Dockerfile` | `docforge-bge-server:latest` | torch/FlagEmbedding; volume `bge_models` |
| mcp | `mcp/Dockerfile` | `docforge-mcp:latest` | ~150 MB pure HTTP client; in-container root `/app/mcp` |

Build example: `docker build -f src/<x>/Dockerfile -t <image> src`. All Dockerfiles are multi-stage
(uv `py-build` + minimal runtime) and **fully commented in English** (docker.md).

## Compose & env

- Prod `docker-compose.yml` + dev override `docker-compose.dev.yml` (source volume mounts + `--reload`;
  dev only overrides what differs, never a full re-def). Services: docforge, worker, mcp, bge_server,
  postgres, qdrant, redis, seaweedfs, gotenberg, pgadmin.
- `services/<svc>/.env` per service (`.env.example` tracked, `.env` gitignored). Provider URLs/secrets
  are NEVER in `.env` — per-collection in DB. Canonical names aligned src↔compose↔services↔hostname
  (see [[naming-and-agent-homogenization]] user memory): bge host `http://bge_server:80`.

## Dev hot-reload (docker-compose.dev.yml) — ALL services reload

`watchfiles` ships with `uvicorn[standard]` (in common, mcp, bge requirements) → no extra deps.
`WATCHFILES_FORCE_POLLING=true` is set on each watcher (WSL2 inotify on Windows bind mounts is unreliable).

| Service | Mechanism |
|---|---|
| docforge | `uvicorn --reload --reload-dir /app/backend --reload-dir /app/common` |
| frontend | Vite dev server + HMR (`:10023`), separate dev-only service |
| worker | `arq entrypoint.WorkerSettings --watch /app` (arq built-in; watches common+worker) |
| mcp | `watchfiles "python entrypoint.py" /app/mcp` (restart wrapper; boots <1s) |
| bge_server | `uvicorn app:app --reload --reload-dir /app` — **a reload RE-LOADS ~4.4 GiB models** (slow); app.py rarely changes so OK, comment out to disable |

Validated with `docker compose -f docker-compose.yml -f docker-compose.dev.yml config` (exit 0).

## Explicit container naming

`name: docforge` is set at the top of `docker-compose.yml` to fix the compose project name.
Every service also has an explicit `container_name:` (set once in the base file; dev override
inherits it — `frontend` is the exception, named only in `docker-compose.dev.yml`):

| Service | container_name |
|---|---|
| docforge | `docforge-app` |
| worker | *(none — scalable; Compose auto-generates `docforge-worker-1`, `-2`, …)* |
| postgres | `docforge-postgres` |
| seaweedfs | `docforge-seaweedfs` |
| gotenberg | `docforge-gotenberg` |
| redis | `docforge-redis` |
| qdrant | `docforge-qdrant` |
| bge_server | `docforge-bge-server` |
| pgadmin | `docforge-pgadmin` |
| mcp | `docforge-mcp` |
| frontend (dev only) | `dev-docforge-app-frontend` |

Service names (DNS hostnames on `docforge_net`) are UNCHANGED — only container display names differ.
`docker compose exec <service-name>` still works as before.

## Known gotchas

- OneDrive dehydrated placeholders break BuildKit ("invalid file request") — materialize (pin local)
  before building; Docker Desktop engine can flap with 500s. See [[onedrive-placeholder-buildkit]].
- docling is worker-only (lazy-imported inside `DoclingBackend.parse`) — never let it into the app image.
- Validate with `docker compose config` before declaring done.

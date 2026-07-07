# Infra — Memory Index

Containerization & deployment for the ACTIVE product `src/docforge-rework/` (being renamed `docforge`).
Docker + docker compose (v2). Legacy `src/docforge/` still has its own `docker-compose.yml` /
`.dev.yml` / `.gpu.yml` but that stack is FROZEN — new work targets the `rework` composes.

## Images (build context `src/docforge-rework`)

| Service | Dockerfile | Image | Notes |
|---|---|---|---|
| rework_app (API) | `app/Dockerfile` | `docforge-rework-app:latest` | light — no docling; serves the frontend |
| rework_worker | `worker/Dockerfile` | `docforge-rework-worker:latest` | heavy — docling; runs the pipeline + IR→DB persistence |

Both Dockerfiles are multi-stage (uv build + minimal runtime), fully commented in English (docker.md).

## Compose (three-layer)

- `docker-compose.rework.yml` — base: `rework_app`, `rework_worker`, `rework_postgres`,
  `rework_redis`, `rework_qdrant`, `rework_seaweedfs`, `rework_gotenberg`. Container names
  `docforge-rework-<svc>`.
- `docker-compose.rework.dev.yml` — hot reload: app/worker mount the source tree
  (`uvicorn --reload --reload-dir /app/app --reload-dir /app/shared`; `arq … --watch /app`); the Vite
  frontend runs as its OWN dev-only service `rework_frontend` (`docforge-rework-frontend`, port
  `10046:5173`, proxy → `http://rework_app:8000`).
- `docker-compose.rework.gpu.yml` — GPU opt-in, layered LAST: grants `rework_worker` `gpus: all`.

Run: base `docker compose -f docker-compose.rework.yml up -d`; +dev add `-f docker-compose.rework.dev.yml`;
+gpu add `-f docker-compose.rework.gpu.yml`. Validate with `docker compose … config` (exit 0) before done.

## Dev host ports (firewall opens 10000–11000)

| Purpose | Host:Container |
|---|---|
| Public API | `10040:8000` |
| Postgres | `10041:5432` |
| Redis | `10042:6379` |
| Qdrant (REST) | `10043:6333` |
| SeaweedFS (S3) | `10044:8333` |
| Gotenberg | `10045:3000` |
| Vite dev UI (dev only) | `10046:5173` |

## Env & secrets

`services/<svc>/.env` per service (`.env.example` tracked, `.env` gitignored). Provider URLs/secrets
are NEVER in `.env` — per-collection in DB.

## Sibling deployables (own composes, NOT in the rework stack)

`src/mcp/` (pure HTTP client → **mcp** agent) and `src/bge_server/` (local model host → **bge-server**
agent) are wired separately. Don't add them to `docker-compose.rework.yml` without being asked.

## Known gotchas

- docling is worker-only — never let it into the app image.
- OneDrive dehydrated placeholders break BuildKit ("invalid file request") — materialize before building.
- No topic files under this agent yet; add one only when a durable infra fact is worth extracting.

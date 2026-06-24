# DocForge Agent — Memory Index

Component: **`src/docforge/`** — THE PRODUCT (app + worker + common socle, deployed together).
This is the orientation memory; deep review/debug knowledge lives in the role agents (see pointers).

## Layout (one product, two apps, one socle)

| Tree | Namespace / import | Runs as | Image |
|---|---|---|---|
| `docforge/common/` | `from common_libs.<bucket> import …` (+ `base_config`, `migrations`) | both | shared deps |
| `docforge/app/` | `from backend.libs.<x> import …` (FastAPI `backend.*`) | uvicorn | `docforge:latest` (light, no docling) |
| `docforge/worker/` | `from libs.<x> import …` | `arq entrypoint.WorkerSettings` | `docforge-worker:latest` (+ docling) |
| `docforge/tests/` | run from `src/docforge/` | pytest | — |

- **Layer DAG:** `domain(0) ← config(1) ← providers(1) ← storage(2) ← search(2) ← pipeline(3)`. A layer
  never imports one above it. Stages (S0→S6) live in `common_libs/pipeline/stages/` (the shared
  `pipeline/assembly` registry imports them statically), NOT in worker.
- **Config by inheritance:** `BaseRuntimeConfig` (`common/base_config/`) holds only vars the shared
  libs read; each app's `config/RUNTIME_CONFIG(BaseRuntimeConfig)` adds its own (app: FASTAPI_*/CORS/
  SSE_*/ADMISSION_*; worker: WORKER_*/OBS_METRICS_*). `from config import RUNTIME_CONFIG` resolves
  per-app. Both entrypoints bootstrap `sys.path` (`docforge/common` + own dir) BEFORE importing config.
- **The app never ingests:** it enqueues an arq job; the worker runs the pipeline.

## Commands

- Dev: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d` (or `/dev`).
- Unit tests: from `src/docforge/` → `uv run --project common pytest tests/units` (or `/test`). If
  `uv run` complains, `unset VIRTUAL_ENV` first (a stale env points at the mcp venv).
- Migrations: `docker compose exec docforge sh -c 'cd /app/common && alembic upgrade head'`.

## Non-negotiable invariants (orientation — full checklist in the code-reviewer agent)

- IR is canonical; providers hide behind a `Protocol`; provider URL+secret are PER-COLLECTION (DB),
  never `.env`; `DeviceManager` owns all GPU/CPU logic; Qdrant holds only filterable fields.
- New env var → shared in `BaseRuntimeConfig`, app/worker-only in the per-app `RUNTIME_CONFIG` + the
  matching `services/docforge/.env`. Schema change → Alembic migration in `common/migrations/versions/`.

## Sibling components (separate agents)

- **`bge_server`** (`src/bge_server/`) — local model host docforge embeds/reranks against → `bge-server` agent.
- **`mcp`** (`src/mcp/`) — pure HTTP client over the REST API → `mcp` agent.

## You are the integrator — route code/work to the right agent

Craftsmen (clean code): React UI → **frontend**; FastAPI web+data → **backend**.
Ultra-specialists (complex): ingestion engine S0→S6 + providers/chains → **pipeline**; test apparatus →
**test**; compose/orchestration choices → **infra**.
Cross-cutting: rules/quality gate → **code-reviewer**; Alembic + SQLAlchemy schema → **migration-engineer**.
Sibling deployables: **mcp** (`src/mcp/`), **bge-server** (`src/bge_server/`).
You own the *conditionnement*: entrypoints, config split, the app+worker Dockerfiles, structure.

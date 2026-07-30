# DocForge Agent — Memory Index

Component: **`src/docforge-rework/`** — THE ACTIVE PRODUCT (app + worker + shared engine, deployed
together; being renamed `docforge`). `src/docforge/` is FROZEN legacy. This is the orientation memory;
deep review/debug knowledge lives in the role agents (see pointers).

## Layout (one product, three roots)

| Root | Namespace / import | Runs as | Role |
|---|---|---|---|
| `shared/` | `from shared_libs.<bucket> import …` | both | pure graph engine (`pipelines/`), `public_models/ir`, `services/db` façade |
| `app/` | `backend.*` | uvicorn | FastAPI (routers pipelines/collections/documents/explorer/jobs/blobs) + frontend |
| `worker/` | `backend.libs.*` | arq | `runner/` (runs the pure pipeline) · `persistence/` (IR→DB translator) · `jobs/` |

- **Pure graph engine:** a node is pure (`NodeConfig` + Consume→Produce, zero DB/S3 I/O); persistence
  happens at the edges in the worker via the `Database` façade. Engine lives in `shared/libs/pipelines/`
  (base/engine/edit/validation/nodes/ingest). Reference doc: `src/docforge-rework/PIPELINE.md`;
  cheat-sheet: `.claude/rules/architecture.md`.
- **Config:** `config` (→ `RUNTIME_CONFIG`) imports FIRST in each entrypoint — it registers the
  `shared_libs` alias and puts `backend/libs` on `sys.path` (`RuntimePathHelpers`). Web-only vars in
  `app/config/runtime_config.py`, worker-only in `worker/config/runtime_config.py`.
- **The app never ingests:** it enqueues an arq job; the worker runs the pipeline.

## Commands (from `src/docforge-rework/`)

- Units: `uv run pytest tests/units` (subtrees api/edit/engine/nodes/stages/validation/worker).
  Live (stack up): `uv run pytest -m live`. Lint: `uv run ruff check .`; types: `uv run mypy .`.
- Dev stack: `docker compose -f docker-compose.rework.yml up -d` (services `rework_app`,
  `rework_worker`, `rework_postgres`, `rework_redis`, `rework_qdrant`, `rework_seaweedfs`,
  `rework_gotenberg`). Dev ports: API 10040 · postgres 10041 · redis 10042 · qdrant 10043 ·
  seaweedfs 10044 · gotenberg 10045.
- Migrations: `docker compose -f docker-compose.rework.yml exec rework_app sh -c 'alembic upgrade head'`
  (versions in `shared/migrations/versions/`).

## Non-negotiable invariants (orientation — full checklist in the code-reviewer agent)

- IR is canonical; providers hide behind a family/kind node contract; provider URL+secret are
  PER-COLLECTION (DB), never `.env`; device is a deployment decision (never a per-collection field);
  Qdrant holds only filterable fields; a broken blob returns as data, never HTTP error.

## Route code/work to the right agent

React UI → **frontend**; FastAPI web+data + `services/db` façade → **backend**; ingestion engine
(nodes/families/graph) → **pipeline**; test apparatus → **test**; compose/orchestration → **infra**;
rules/quality gate → **code-reviewer**; Alembic + SQLAlchemy tables → **migration-engineer**. Sibling
deployables: **mcp** (`src/mcp/`), **bge-server** (`src/bge_server/`). You own the *conditionnement*:
entrypoints, config split, the app+worker Dockerfiles, structure.

## Assembly facts

- [Worker torch cpu/gpu variants](worker_torch_variants.md) — worker image cpu/gpu torch wheel selection: how the deps contract steers transitive docling torch to the right wheel index; validate gpu via `uv export`, not `--dry-run`.
- [docforge-sdk package](docforge-sdk-package.md) — standalone installable client lib (package=true, httpx+pydantic only, zero docforge-rework dep), MCP consumes it later

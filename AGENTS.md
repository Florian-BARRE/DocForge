# AGENTS.md — DocForge

Repo-specific notes for coding agents. Generic agent rules (planning, review, memory, definition of
done) come from the dev environment's managed layer, not from this file.

## What DocForge is

A document intelligence platform: any document (PDF, Office, images…) becomes a canonical
intermediate representation (IR), is enriched, chunked, embedded (BGE-M3, Qdrant) and served through
hybrid search — behind a REST API, a typed Python SDK (`docforge-sdk`) and an MCP server. See
`README.md` and `docs/architecture.md`.

## Layout

- `src/docforge/` — the product (one uv project): `app/` (FastAPI backend + React/Vite frontend in
  `app/frontend/`), `worker/` (arq worker), `shared/libs/` (pure graph engine, IR models, `Database`
  façade), `tests/` (`units`, `db`, `live`, `rag_eval`), `PIPELINE.md` (living pipeline reference).
- `src/docforge_sdk/` (published client), `src/mcp/` (MCP server over the SDK), `src/bge_server/`,
  `src/paddle_server/`, `src/mineru_server/`, `src/dots_ocr_server/` (model hosts).
- `compose/` — compose scenarios and overlays, indexed in `compose/README.md`.
- `services/` — per-service config: gitignored `.env` files next to committed `.env.example` templates.
- `docs/` — product docs (`docs/archive/` is frozen legacy prose).

## Checks (as CI runs them, `.github/workflows/gate.yml`)

Run from the package directory you touched:

```bash
# src/docforge (no mypy for this package; needs services/docforge/.env, CI copies the .env.example)
uv sync --frozen
uv run ruff format --check . && uv run ruff check .
uv run pytest tests/units -q --cov=app --cov=worker --cov=shared --cov-report=term-missing
uv run python -m pytest tests/rag_eval -q -m "not live"
uv run pytest tests/db -m db -q              # needs a real Postgres (TEST_POSTGRES_* env vars)

# src/docforge_sdk
uv sync --frozen && uv run ruff format --check . && uv run ruff check .
uv run mypy --strict docforge_sdk && uv run pytest -q -m "not live"

# src/mcp
uv sync --frozen && uv run ruff format --check . && uv run ruff check .
uv run mypy . && uv run pytest -q

# src/bge_server, src/paddle_server (CPU wheels, then never re-sync)
uv sync --frozen --extra cpu
uv run --no-sync ruff format --check . && uv run --no-sync ruff check .
uv run --no-sync mypy . && uv run --no-sync pytest -q

# src/docforge/app/frontend
npm ci && npm run lint && npx tsc --noEmit && npm run test && npm run build
```

After touching anything under `compose/`: `make config-check-all` (repo root).

## Conventions

- Python modules open with a `# ====== Code Summary ======` comment block, then import sections in
  this order: `# ====== Standard Library Imports ======`, `# ====== Third-Party Library Imports ======`,
  `# ====== Internal Project Imports ======`, `# ====== Local Project Imports ======` (relative
  imports). Match the file you edit.
- Google-style docstrings, type hints everywhere, English for code, comments and commits.
- Commits: `type(scope): summary` (`feat`, `fix`, `docs`, `test`, `ci`, `refactor`, `chore`).
- This is a public repo. No AI attribution trailers in commits, no AI tool setup files and no
  pointers to internal agent paths in tracked files:
  `src/docforge/tests/units/coherence/test_no_internal_artifacts_leak.py` fails the gate otherwise.

## Invariants and caveats

- The IR is canonical; Markdown/PDF/HTML are generated views (`README.md`).
- Pipeline nodes are pure: `Config` + Consume → Produce, no DB/S3 I/O; persistence happens in the
  worker through the façades (`docs/architecture.md` §3, §4).
- Provider URLs and secrets live per collection in the DB, never in `.env` (`docs/architecture.md` §4).
- Blob validation checks topology and config shape, not connectivity (`docs/architecture.md` §3).
- A backend router model change must keep the SDK in sync (OpenAPI snapshot + SDK models), or CI's
  `sdk-parity` job fails (`CONTRIBUTING.md`).
- Doc ratchets in `src/docforge/tests/units/coherence/test_doc_coherence.py`: every ingest node kind in
  `PIPELINE.md`, every API route in `docs/rest-api.md`, every env var in `docs/configuration.md`,
  backticked repo paths in the top-level docs must exist, compose files keep the `compose.*.yml` name.

## Dev stack (dev center: main checkout and each worktree)

Driven by `scripts/dev-stack.sh` (compose files `compose/compose.dev-cpu.yml` +
`compose/overlays/compose.worktree.yml`, details in `compose/README.md`):

```bash
scripts/dev-stack.sh setup      # worktree: port block, .env.worktree, DB copied from main, up
scripts/dev-stack.sh up         # start or update
scripts/dev-stack.sh rebuild    # rebuild images and restart, data kept
scripts/dev-stack.sh url        # address of the app
scripts/dev-stack.sh status     # address, containers, logs
scripts/dev-stack.sh teardown   # worktree only: containers, volumes and ports removed
```

- Core CPU services start by default (app, worker, postgres, redis, qdrant, seaweedfs, gotenberg).
  Opt in with `COMPOSE_PROFILES=models` (bge_server, paddle_server) and/or `extras` (mcp, Vite
  frontend), e.g. `COMPOSE_PROFILES=models,extras scripts/dev-stack.sh up`. The host is shared:
  check free memory (`free -h`) before enabling `models`.
- After a change that affects what runs, `scripts/dev-stack.sh rebuild`, then check the page at the
  URL printed by `scripts/dev-stack.sh url`, and give that URL in your report.
- Dev env files (`.env`, `services/*/.env`, `.env.worktree`) are gitignored, created from the
  committed `.example` files, and never committed.
- Do not mix `make up-dev-cpu` and `scripts/dev-stack.sh` in the same checkout: both use the same
  compose project name.

# DocForge — rules for coding agents

<!-- aidk:begin · the AI Dev Kit's block: aidk project upgrade rewrites it; edit the rest of this file -->
## AI Dev Kit

This project runs on the AI Dev Kit and Orca, with any agent. **Before anything else, and again after a
context compaction, run `aidk guide`**: it prints your role here (the project-leader in the main checkout,
a worker in a worktree) and its method.

- Memory: `aidk memory search "<words>"` before deciding; `aidk memory save` for what lasts.
- A task ends with `aidk done` (checks, push, request), never by declaring it done.
- A question only the user can settle: `aidk inbox ask "<question>"`.
- Skills: `aidk skill list` (the kit's; this project has none of its own yet).
<!-- aidk:end -->

Read by every agent session (Claude Code through `CLAUDE.md`, Codex directly). Project-specific
facts only; generic agent rules (planning, delegation, commits, review, memory, definition of done)
come from the dev center's managed layer. All checks: `aidk verify` from the repository root (they
live in `.aidk/project.toml`).

## General

- Code, comments, commit messages and pull request text in English.
- Commits: `type(scope): summary` (feat, fix, docs, test, refactor, chore, ci).
- Never commit secrets: `.env` files stay local; `.env.example` lists the variables.

## What it is

A document intelligence platform: any document (PDF, Office, images…) becomes a canonical
intermediate representation (IR), is enriched, chunked, embedded (BGE-M3, Qdrant) and served through
hybrid search — behind a REST API, a typed Python SDK (`docforge-sdk` on PyPI) and an MCP server.
Production runs the published GHCR images with `compose/compose.prod-cpu.yml` (`docs/deployment.md`).
Public repository.

## Layout

- `src/docforge/` — the product (one uv project): `app/` (FastAPI backend + React/Vite frontend in
  `app/frontend/`), `worker/` (arq worker), `shared/libs/` (pure graph engine, IR models, `Database`
  façade), `tests/` (`units`, `db`, `live`, `rag_eval`), `PIPELINE.md` (living pipeline reference).
- `src/docforge_sdk/` (published client), `src/mcp/` (MCP server over the SDK), `src/bge_server/`,
  `src/paddle_server/`, `src/mineru_server/`, `src/dots_ocr_server/` (model hosts). Each is its own uv
  project with its own `uv.lock`.
- `compose/` — compose scenarios and overlays, indexed in `compose/README.md`.
- `services/` — per-service config: gitignored `.env` files next to committed `.env.example` templates.
- `docs/` — product docs, indexed in `docs/README.md` (`docs/archive/` is frozen legacy prose);
  `docs/architecture.md` is the reference for the engine, storage and quality gates.

## Code conventions (not enforced by the linters)

- Python modules open with a `# ====== Code Summary ======` comment block, then import sections in
  this order: `# ====== Standard Library Imports ======`, `# ====== Third-Party Library Imports ======`,
  `# ====== Internal Project Imports ======`, `# ====== Local Project Imports ======` (relative
  imports). Match the file you edit.
- Google-style docstrings and type hints (`src/docforge` has no mypy).

## Invariants

- The IR is canonical; Markdown/PDF/HTML are generated views (`README.md`).
- Pipeline nodes are pure: `Config` + Consume → Produce, no DB/S3 I/O; persistence happens in the
  worker through the façades (`docs/architecture.md` §3, §4).
- Provider URLs and secrets live per collection in the DB, never in `.env` (`docs/architecture.md` §4).
- Blob validation checks topology and config shape, not connectivity (`docs/architecture.md` §3).

## If you change X, also change Y

| Change | Also | Enforced by |
|---|---|---|
| a backend router model (`src/docforge/app/backend/routers/**/models.py`) | the OpenAPI snapshot and the SDK models (and the MCP tool for a new endpoint), steps in `CONTRIBUTING.md` | `sdk-parity` check |
| an ingest node kind | `src/docforge/PIPELINE.md` | `test_doc_coherence.py` |
| an API route | `docs/rest-api.md` | `test_doc_coherence.py` |
| an env var of the app or worker config | `docs/configuration.md` | `test_doc_coherence.py` |
| a repo path named in backticks in the top-level docs | the doc (the path must exist) | `test_doc_coherence.py` |
| a compose file | keep the `compose.*.yml` name; run `make config-check-all` (Docker, not in `aidk verify`) | `test_doc_coherence.py` |
| a service in `compose/compose.base.yml` or `compose/overlays/compose.dev.yml` | `compose/overlays/compose.worktree.yml` (container name, ports, profile) | `test_worktree_compose_overlay.py` |
| the version | `scripts/set_version.sh X.Y.Z` (docforge, mcp and SDK in lockstep; bge and paddle version on their own) | `test_version_alignment.py` |

These tests live under `src/docforge/tests/units/` (`coherence/` for the first ones).

## Public repository: never

- No AI attribution trailers in commits or tracked files, and no tracked AI tool setup: `CLAUDE.md`,
  `.claude/` and `.mcp.json` stay local and gitignored (`.worktreeinclude` copies `CLAUDE.md` and
  `.claude/settings.json` into each worktree); `test_no_internal_artifacts_leak.py` fails the gate otherwise.
- gitleaks scans the commits (`.gitleaks.toml`: test dirs and `docs/rest-api.md` allowlisted); mark a
  deliberate fake secret elsewhere with an inline `# gitleaks:allow` comment.
- Never push a `v*` or `sdk-v*` tag: a tag publishes the images (GHCR) and the SDK (PyPI) through
  `release-sdk.yml`.

## Pitfalls

- `src/bge_server`, `src/paddle_server`: sync with `--extra cpu`, then `uv run --no-sync`, or uv
  re-resolves torch/paddle to the multi-GB CUDA build.
- `tests/rag_eval` runs as `python -m pytest` (it imports `tests.rag_eval.*`; `tests/` has no `__init__`).
- `tests/db` (`-m db`) needs a real Postgres (`TEST_POSTGRES_*`): only the CI's `db-tests` job runs it.
- The `src/docforge` suite reads `services/docforge/.env` at import; `aidk verify` uses the
  `.env.example` instead, as the CI does.

## Dev stack (dev center: main checkout and each worktree)

Driven by `scripts/dev-stack.sh` (compose files `compose/compose.dev-cpu.yml` +
`compose/overlays/compose.worktree.yml`, details in `compose/README.md`):

```bash
scripts/dev-stack.sh setup      # worktree: port block, .env.worktree, DB copied from main, up
scripts/dev-stack.sh up         # start or update
scripts/dev-stack.sh rebuild    # rebuild images and restart, data kept (after a change that affects what runs)
scripts/dev-stack.sh url        # address of the UI (Vite frontend)
scripts/dev-stack.sh status     # address, containers, logs
scripts/dev-stack.sh teardown   # worktree only: containers, volumes and ports removed
```

- Core CPU services start by default (Vite frontend, app, worker, postgres, redis, qdrant,
  seaweedfs, gotenberg). Opt in with `COMPOSE_PROFILES=models` (bge_server, paddle_server) and/or
  `extras` (mcp), e.g. `COMPOSE_PROFILES=models,extras scripts/dev-stack.sh up`. The host is
  shared: check free memory (`free -h`) before enabling `models`.
- The UI is the Vite frontend (hot reload) at the URL printed by `scripts/dev-stack.sh url` (first
  port of the block; `10046` in main); it proxies the API calls to the app. The API is on the next
  port (`API_PORT` in `.env.worktree`; `10040` in main), API docs at `/scalar`; its `/` is 404 in dev
  (the source mount hides the built UI). The frontend's first start runs `npm ci` (a few minutes) and
  `up --wait` does not wait for it: retry the page if it is not up yet.
- `services/docforge/s3_config.json` must be mode 644 (rootless Docker cannot read a 600 file in a
  private checkout): otherwise seaweedfs's S3 dies with "permission denied" and the app fails at startup.
- Never `make up-*` / `down-*` on the dev center (main checkout or worktree): fixed compose project
  `docforge` and fixed container names, so a worktree would take over main's stack. The Makefile
  scenarios are for contributors' machines.

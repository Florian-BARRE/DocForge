# Test — Memory Index

Tests for the ACTIVE product live in `src/docforge-rework/tests/` (being renamed `docforge`). Single
uv project — no multi-root `--project` dance.

## Run commands (from `src/docforge-rework/`)

- Units: `uv run pytest tests/units` — subtrees `units/{api,edit,engine,nodes,stages,validation,worker}`,
  fully mocked.
- Single test: `uv run pytest tests/units/engine/test_x.py::T::test_m`.
- Live (stack up): `uv run pytest -m live` — real ingestion; auto-skips when the stack is unreachable.
- Lint / types: `uv run ruff check .` · `uv run mypy .`.

## Traps

- **`NodeRegistry` is process-global** (`shared_libs.pipelines.registry`) — fake/test nodes MUST use a
  session-unique KIND string, or collection crashes the whole session. See [[noderegistry-global-state]].
- `tests/conftest.py` installs the `shared_libs` alias + worker `backend.libs` path exactly ONCE, and
  boots the app lazily for API tests — mirror it, don't re-register. See [[bootstrap-mechanics]].
- First import of `app/entrypoint.py` in a fresh process is ~30s (cold module import, not a real DB
  connection) — size subprocess timeouts generously. See [[app-boot-cold-import-cost]].

## Conventions

- Units mock at the boundary (façade/client/node) — never touch Postgres/Qdrant/S3.
- Assert exact HTTP status codes for every rejection/mutation path. New route/field/branch ships with
  its test in the same change.
- A broken pipeline blob is tested as DATA (`valid=false` + issues), not an HTTP error.

## Topic files

- [NodeRegistry global state](noderegistry-global-state.md) — the process-global registry; use a session-unique KIND string in fakes or collection crashes.
- [Bootstrap mechanics](bootstrap-mechanics.md) — how `tests/conftest.py` bootstraps `shared_libs` + worker libs without colliding with the app namespace, and lazy app boot for API tests.
- [App boot cold-import cost](app-boot-cold-import-cost.md) — the ~30s first import of `app/entrypoint.py`; size subprocess timeouts accordingly.
- [Stage combinatorics strategy](stage-combinatorics-strategy.md) — hitting all 2^5=32 optional-stage toggle combinations directly, bypassing StageCompiler's dependency cascade.
- [Scratchpad port complete](scratchpad-port-complete.md) — the scratchpad→pytest port DONE (2026-07-05): final counts + the one live-stack infra gap (S3 bucket not provisioned).
- [Port scratchpad gap plan](port-scratchpad-gap-plan.md) — the (now-executed) 1:1 mapping of scratchpad spec scripts to source + the file list that was still to write; historical, read before re-deriving.

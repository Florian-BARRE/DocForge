---
name: test
description: Run the DocForge test suite
user-invocable: true
allowed-tools: "Bash(*), Read(*)"
---

# Run Tests

Run the DocForge test suite. The tree is **multi-root** (`src/docforge/{common,app,worker}`):
pytest runs from `src/docforge/` (config in `pytest.ini`); the deps-only project lives in `common/`,
so use `--project common`. `tests/conftest.py` bootstraps `sys.path` for all roots.

## Steps

1. **Unit suite** (default — fast, fully mocked, no services needed):
   ```bash
   cd src/docforge && unset VIRTUAL_ENV && uv run --project common pytest tests/units -q --tb=short $args
   ```
   (`unset VIRTUAL_ENV` avoids a stale env var pointing at another project's venv.)

2. **Live suite** (ONLY on explicit request — needs the full stack `up` AND the `bge_server` model
   service ready at http://localhost:10026/health):
   ```bash
   cd src/docforge && unset VIRTUAL_ENV && uv run --project common pytest tests/live_test -q --tb=line
   ```
   Auto-skips when the stack is unreachable; ingestion runs through `bge_server` (slow on CPU).

3. **Report results** — list failures with file:line and the error message.

Arguments: `$args` — optional pytest args (e.g., `-k test_ir`, `-x`, `tests/units/test_chunking.py`).

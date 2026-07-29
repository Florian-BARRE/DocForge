---
name: test
description: Run the DocForge test suite
user-invocable: true
allowed-tools: "Bash(*), Read(*)"
---

# Run Tests

Run the DocForge test suite. `src/docforge-rework/` is a **single autonomous uv project** with 3
roots (`shared/`, `app/`, `worker/`); `tests/conftest.py` installs the `shared_libs` alias once
(the `NodeRegistry` is process-global — a double alias would break it).

## Steps

1. **Unit suite** (default — fast, fully mocked, no services needed):
   ```bash
   cd src/docforge-rework && uv run pytest tests/units -q --tb=short $args
   ```

2. **Live suite** (ONLY on explicit request — needs the full stack `up` AND `bge_server` ready at
   http://localhost:10047/health):
   ```bash
   cd src/docforge-rework && uv run pytest -m live -q --tb=line
   ```
   Ingestion runs through `bge_server` (slow on CPU).

3. **Lint / typecheck** (on request): `cd src/docforge-rework && uv run ruff check . && uv run mypy .`

4. **Report results** — list failures with file:line and the error message.

Arguments: `$args` — optional pytest args (e.g., `-k test_ir`, `-x`, `tests/units/engine/test_x.py`).

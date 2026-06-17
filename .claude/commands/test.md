---
name: test
description: Run the DocForge test suite
user-invocable: true
allowed-tools: "Bash(*), Read(*)"
---

# Run Tests

Run the full DocForge test suite using uv + pytest.

## Steps

1. **Locate test files**:
   ```bash
   find src/docforge -name "test_*.py" -o -name "*_test.py" | sort
   ```

2. **Run tests**:
   ```bash
   cd src/docforge && uv run pytest tests/ -v --tb=short 2>&1 | head -100
   ```

3. **Report results** — list failures with file:line and error message.

4. **If no tests exist yet** — report that and list test files that should be created based on the current code.

Arguments: `$args` — optional pytest args (e.g., `-k test_ir`, `-x`, `--cov`)

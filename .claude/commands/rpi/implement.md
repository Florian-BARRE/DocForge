---
name: rpi:implement
description: >-
  Implement phase — execute the plan from /rpi:plan for a DocForge feature.
  Follows the plan step by step, runs tests, and invokes the code-reviewer agent.
model: opus
allowed-tools: ["Read", "Write", "Edit", "Bash", "Agent"]
user-invocable: true
argument-hint: "<feature-slug>"
---

# RPI — Implement Phase

Execute the implementation plan for a DocForge feature. Requires a plan from `/rpi:plan`.

## Steps

### 1. Load the plan

```bash
cat docs/rpi/$args/plan.md
```

If no plan exists, refuse and ask to run `/rpi:plan` first.

### 2. Implement new files

For each new file in the plan:
- Follow python.md rules strictly (LoggerClass, f-string logs, import order, Code Summary)
- Follow fastapi.md rules for any new routers (@auto_handle_errors, response_model)
- Add the `# ====== Code Summary ======` header
- Write Google-style docstrings on all public methods

### 3. Modify existing files

For each modified file:
- Minimal diff — only change what the plan requires
- If modifying `engine.py`, add the DAG node in the correct position (S0→S1→S2→S4→S5→S6)
- If modifying `lifespan.py`, update `TOTAL_STEPS` and add `hasattr` guard in `finally`
- If modifying `RUNTIME_CONFIG`, add the new env var with a sensible default

### 4. Alembic migration

If the plan requires a schema change:
```bash
cd src/docforge && uv run alembic revision --autogenerate -m "<description>"
# Review the generated migration, then run:
uv run alembic upgrade head
```

### 5. Run tests

```bash
cd src/docforge && uv run pytest tests/ -v --tb=short 2>&1 | tail -30
```

Fix any failures before proceeding.

### 6. Code review gate

Spawn the `code-reviewer` agent on all changed files:
```
Review these files for DocForge rule compliance: <list of changed files>
```

If the reviewer returns NEEDS REVISION, fix the issues and run again.

### 7. Update documentation

- Add new env vars to `services/docforge/.env` with defaults
- Update `CLAUDE.md` phase table if this is a new phase
- Save implementation notes to `docs/rpi/$args/implementation.md`

### 8. Summary

Report:
- Files created: <list>
- Files modified: <list>
- New env vars: <list>
- Migration: <filename or "none">
- Test result: PASSED / FAILED
- Review: APPROVED / APPROVED WITH SUGGESTIONS

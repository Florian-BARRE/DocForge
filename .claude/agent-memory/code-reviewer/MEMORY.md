---
name: code-reviewer-memory
description: DocForge-specific code review checklist, anti-patterns, and past findings
metadata:
  type: project
---

# Code Reviewer Memory

## Non-negotiable rules (from feedback)

- **Podman only** — never write `docker`, `docker-compose`, `docker build` in any context
- **SeaweedFS only** — never write MinIO anywhere
- **loggerplusplus only** — no `print()`, no direct loguru import
- **LoggerClass.__init__(self) required** — every subclass must call it explicitly
- **RUNTIME_CONFIG first** — always the first internal import in entry points
- **English only** — all code, comments, docstrings, variable names

## Review checklist — Python (python.md)

- [ ] Every instanciable class: inherits `LoggerClass`, calls `LoggerClass.__init__(self)`
- [ ] No `print()` or `import loguru` anywhere in application code
- [ ] All log messages are f-strings: `self.logger.info(f"Done")` not `self.logger.info("Done")`
- [ ] Import order: stdlib → third-party → `from config import ...` → relative imports
- [ ] File header: `# ====== Code Summary ======` (except `__init__.py`)
- [ ] `__init__.py`: labeled sections + `__all__`
- [ ] Static helpers class: `__new__` raises `TypeError`, logger bound at class level

## Review checklist — FastAPI (fastapi.md)

- [ ] `@auto_handle_errors` on every route (between `@router.verb` and `async def`)
- [ ] `response_model` declared on every route
- [ ] No business logic in `router.py` — only calls to `CONTEXT.service.method()`
- [ ] `CONTEXT.attr` used for all services — never import instances directly in routers
- [ ] `hasattr(CONTEXT, "attr")` guards in `lifespan.py` `finally` block

## Review checklist — DocForge invariants

- [ ] IR is canonical — no code writes raw markdown/PDF as source of truth
- [ ] Every provider implements its `Protocol` — duck-typed, no concrete coupling
- [ ] No device logic (CUDA/CPU) inside individual providers — only in `DeviceManager`
- [ ] New env vars: added to `RUNTIME_CONFIG` class AND `services/docforge/.env`
- [ ] Schema change: Alembic migration present in `migrations/versions/`
- [ ] New pipeline stage: wired as DAG node in `libs/pipeline/engine.py`
- [ ] New stage: idempotency guaranteed (Postgres ON CONFLICT DO NOTHING, Qdrant upsert)

## Common anti-patterns seen in this codebase

- Passing `collection_id` as a positional arg instead of keyword — causes silent None
- Forgetting `await` on async repo methods — Python won't warn, returns coroutine object
- Hardcoding `http://localhost:8000` instead of using `RUNTIME_CONFIG.DOCFORGE_API_URL`
- Using `os.environ.get()` in application code — must use `RUNTIME_CONFIG` instead
- Returning raw `dict` from a route instead of a Pydantic model

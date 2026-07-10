---
name: test-backend-import-wiring
description: In tests/units/api, defer any `from backend...` import until after the fastapi_app fixture — module-top import fails collection
metadata:
  type: feedback
---

In `tests/units/api/`, the `backend` package is NOT importable at module top level — it only
resolves after the session `fastapi_app` fixture (in `tests/units/api/conftest.py`) inserts
`app/` at the front of `sys.path`.

**Why:** each app has its own `sys.path` wiring done by its `config`/entrypoint; the test harness
reproduces uvicorn's boot lazily via `fastapi_app`. A top-level `from backend.routers... import X`
raises `ModuleNotFoundError: No module named 'backend'` at collection time.

**How to apply:** when unit-testing a helper/DTO/router under `backend.*`, take the `fastapi_app`
fixture (directly or via a small fixture that does the deferred import with `# noqa: PLC0415`) and
import inside the fixture/test body — never at module top. Existing tests
(`test_enablement_routes.py`, `test_search_routes.py`) do `from backend.context import CONTEXT`
inside the test functions for the same reason.

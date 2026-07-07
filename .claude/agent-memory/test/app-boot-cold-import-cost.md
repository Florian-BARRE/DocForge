---
name: app-boot-cold-import-cost
description: The FIRST import of app/entrypoint.py in a fresh process takes ~30s (cold module import over the OneDrive-backed tree, not a real DB connection) — size subprocess timeouts generously.
metadata:
  type: project
---

The first time a fresh Python process imports `app/entrypoint.py`, there is a ~30s gap between
`RuntimePathHelpers: Python path registered` and `PostgresClient connected` in the logs. This is
NOT a real network wait: `shared_libs/services/db/postgresql/client.py::PostgresClient.__init__`
only calls `create_async_engine(...)` (asyncpg pools are lazy — no TCP connection happens at
construction) — the log message "PostgresClient connected" is misleading (it only configured the
pool). The delay is cold-importing sqlalchemy/asyncpg/qdrant_client/aioboto3/langchain for the
first time in the process, plausibly slower than usual because the repo lives under OneDrive
(see the user's global memory: OneDrive placeholder/sync effects have caused build slowness
before). Subsequent imports in the SAME warm process are instant.

**Practical consequence**: `tests/units/api/conftest.py::fastapi_app` is session-scoped (pays
the cost once for the whole `pytest tests/units` run — acceptable). The import-hygiene check
(`tests/units/api/test_app_boot.py::test_import_hygiene_backend_stays_light`) MUST run in an
isolated subprocess (`tests/units/api/_hygiene_probe.py`) — both because other unit tests in the
same session deliberately import docling/rapidocr for real (making an in-process `sys.modules`
check order-dependent garbage), and because that subprocess pays the same cold-import tax. Give
it a generous timeout (120s used here); a 60s timeout flaked on a cold run.

**Also learned**: loggerplusplus writes to stdout by default (`LOGGING_ENABLE_CONSOLE=true`),
so a subprocess probe that needs to report a machine-readable result must print it behind a
unique sentinel prefix (e.g. `HYGIENE_RESULT:...`) and grep for that exact line — raw
`stdout.strip()` will capture interleaved ANSI-colored log lines instead.

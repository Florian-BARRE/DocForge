---
name: bootstrap-mechanics
description: How tests/conftest.py bootstraps shared_libs + worker libs without colliding with the app's own namespace, and how the app is booted lazily for API tests.
metadata:
  type: project
---

`tests/conftest.py` (at `src/docforge-rework/tests/conftest.py`) registers the `shared_libs`
package alias (a `types.ModuleType` with `__path__=[shared/libs]`, mirroring
`app/config/helpers.py::RuntimePathHelpers.register_package_alias`) and adds
`worker/backend/libs` directly to `sys.path` — done exactly ONCE, at collection time, for the
whole session.

**Why only `worker/backend/libs`, never the `worker/` root**: `worker/backend/libs/{runner,
persistence,jobs}` only ever import `shared_libs.*` (verified by inspection) — never the
worker's own `config`/`backend` packages. So adding `worker/backend/libs` to `sys.path` exposes
`runner`/`persistence` as flat top-level imports (`from runner import PipelineRunner`) without
ever registering a `backend` or `config` top-level package for the worker side.

**Why this avoids the app/worker collision**: both `app/` and `worker/` define their own
top-level `backend` and `config` packages. The API test fixture (`tests/units/api/conftest.py`)
inserts `app/` onto `sys.path` and imports `entrypoint.app`, which DOES register `app`'s
`backend`/`config` as the top-level names. As long as `worker/` (the root, not
`worker/backend/libs`) is never also added to `sys.path` in the same process, there is no
collision — confirmed empirically: `tests/units/worker/` (runner/translator tests, not yet
written as of 2026-07-05) and `tests/units/api/` can coexist in one pytest session.

**App boot fixture**: `tests/units/api/conftest.py::fastapi_app` (session-scoped) inserts
`app/` at the front of `sys.path` and does `from entrypoint import app` — exactly like uvicorn
launched from `app/` would. No `os.chdir` needed: `RUNTIME_CONFIG` resolves all paths from
`__file__`, and `LOGGING_ENABLE_FILE=false` in `services/docforge-rework/.env` means no relative
`"logs"` directory is touched.

See also [[noderegistry-global-state]] and [[app-boot-cold-import-cost]].

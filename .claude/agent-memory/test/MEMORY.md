# Test — Memory Index

DocForge tests live in `src/docforge/tests/`. Multi-root pytest with a few non-obvious traps.

## Run commands (from `src/docforge/`)

- Units: `unset VIRTUAL_ENV && uv run --project common pytest tests/units` — **540 tests, fully mocked**.
- Live: `uv run --project common pytest tests/live_test` — needs the stack `up` + `bge_server` ready
  (real ingestion, slow on CPU; auto-skips when unreachable).
- `pytest.ini` + root `conftest.py` are at `src/docforge/`.

## Traps

- `--project common` is required: the deps-only pyproject is in `common/`, not at the docforge root.
- A stale `VIRTUAL_ENV` points at the **mcp** venv → `unset VIRTUAL_ENV` first or `uv run` resolves the
  wrong environment.
- App `libs.*` and worker `libs.*` are distinct namespaces — a single pytest process can't import both
  (documented multi-root follow-up). Keep app-only and worker-only tests from colliding in one run.

## Tree & conventions

- `tests/{units, live_test, libs, fixtures, corpus}`. `libs/` = shared test helpers; `corpus/` = sample
  documents for ingestion fixtures.
- Units mock at the boundary (provider/repo/client) — never touch Postgres/Qdrant/S3/bge_server.
- Assert **exact HTTP status codes** for every rejection/mutation path (the verbose error-handling
  convention — see [[verbose-error-handling-convention]] user memory). New route/field/branch ships
  with its test in the same change.

## Auth layer — fixtures & integration approach (added 2026-06-24)

- `inject_context` in `tests/units/api/conftest.py` now requires `AUTH_ENABLED=False` on the mock
  `RUNTIME_CONFIG` AND must inject `user_repo`, `api_key_repo`, `grant_repo`, `auth_service` into
  CONTEXT. Without these, collection-scoped routes calling `require_collection_role` raise
  `AttributeError: CONTEXT has no attribute 'auth_service'`.
- `mock_auth_service.effective_collection_role` defaults to `GrantRole.ADMIN` (mirrors root behaviour
  when auth is off) — any lower default causes 403s on collection-scoped routes that the existing
  tests never expected to be gated.
- **Auth-on tests** live in `tests/units/api/auth/test_auth_api.py`. They use a local `authed_client`
  fixture that sets `CONTEXT.RUNTIME_CONFIG.AUTH_ENABLED=True` and programs
  `CONTEXT.auth_service.resolve_principal` via a side-effect function. The existing 418 tests keep
  `AUTH_ENABLED=False` — zero header churn.
- Windows/PyJWT quirk: `datetime.now(timezone.utc)` has second-level precision → two tokens minted
  within the same second are byte-identical (same iat/exp). Do NOT test non-determinism with a short
  `sleep`; test structural shape (three dot-separated parts) instead.
- `touch_last_used` assertion: the first positional arg is the session mock (opaque), the second is
  `api_key.id`. Use `call_args.args[1] == api_key.id` rather than `assert_awaited_once_with(...)`.

## Config validate() tests (added 2026-06-24)

- `RUNTIME_CONFIG.validate()` (in `app/config/runtime_config.py`) is tested by monkeypatching
  class-level attributes directly: `monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True, raising=False)`.
  The `_PLACEHOLDER_*` and `_MIN_JWT_SECRET_LEN` sentinel constants are importable from
  `config.runtime_config` (no leading underscore rename) and used in the tests to avoid magic strings.
- Test file: `tests/units/test_runtime_config_validate.py`.

## SSE unit test pattern (added 2026-06-24)

- SSE routes call `SseHelpers.stream(CONTEXT.event_broadcaster, ...)`. Unit tests for SSE auth need
  TWO patches:
  1. `monkeypatch.setattr(CONTEXT, "event_broadcaster", MagicMock(), raising=False)` — CONTEXT doesn't
     have this attribute by default in `inject_context` (only `event_publisher` is wired).
  2. Patch `SseHelpers.stream` on the **already-imported** module reference in the router — use
     `importlib.import_module("backend.routers.monitoring.router")` and then
     `monkeypatch.setattr(_mod.SseHelpers, "stream", staticmethod(_fake), raising=True)`.
     Patching `"backend.libs.utils.sse.SseHelpers.stream"` by string does NOT work because the router
     already holds a local reference from its `from ...libs.utils.sse import SseHelpers` import.
- The fake stream function should return `EventSourceResponse(_empty_gen(), ping=keepalive)` where
  `_empty_gen` is an async generator that returns immediately. This produces HTTP 200 with an empty
  body — enough to assert auth passed without a real broadcaster.
- Also set `CONTEXT.RUNTIME_CONFIG.SSE_KEEPALIVE_SECONDS` via monkeypatch when testing SSE routes
  (the mock RUNTIME_CONFIG doesn't have this attribute by default).

## LiveClient token support (added 2026-06-24)

- `LiveClient.__init__` now accepts `api_token: str = ""`. When non-empty, it sets
  `Authorization: Bearer <token>` as a default header on the underlying `httpx.Client`.
- `collect_sse` appends `?token=<token>` to the URL when a token is set (browser EventSource path).
- `tests/live_test/conftest.py` reads `DOCFORGE_TEST_API_TOKEN` from env (default "") and passes it
  as `api_token=API_TOKEN` to `LiveClient(...)`. Empty = no header (backward compat with auth-off stacks).
- `tests/live_test/test_auth_live.py` is the live auth coverage file. Skip strategy: two levels —
  session-level `live_client` fixture skips when stack is unreachable; tests call `_is_auth_on(client)`
  and skip individually when `AUTH_ENABLED=False`. Env var `DOCFORGE_TEST_ROOT_PASSWORD` is needed
  for login tests; `DOCFORGE_TEST_API_TOKEN` for RBAC/key/SSE tests.
- Do NOT use `@pytest.mark.live` on live test classes — `live` is not a registered mark in `pytest.ini`
  and will produce PytestUnknownMarkWarning. Use inline `pytest.skip()` instead.

## Live conftest — collection naming + keep flag (added 2026-06-25)

- Collection naming: `e2e-{label}-{YYYYMMDD-HHMMSS}` using `datetime.now().strftime("%Y%m%d-%H%M%S")`.
  `make_collection` uses the pytest test node name as label by default (requires `request` fixture
  injection); callers pass `label=` to override. `ingested_corpus` uses the stable label `corpus`.
- `make_collection` signature: `_make(label: str | None = None, **overrides)`. `name=` override still
  works but bypasses the timestamp naming — prefer `label=` for human-readable names.
- `IngestedCorpus` dataclass now carries `collection_name: str` (the full `e2e-corpus-*` name).
- Cleanup opt-out: `DOCFORGE_TEST_KEEP_COLLECTIONS=true` (or `1`/`yes`) skips deletion and prints
  `[KEPT] collection id=... name=...` for each kept collection. Default: delete on teardown.

## Document artifact unit coverage (added 2026-06-25)

- `tests/units/api/collections/documents/files/test_files.py` now covers:
  - `TestGetFigureCrop`: figures/{block_id} → 200 (blob present), 404 (blob missing), 409 (not done), 404 (unknown doc).
  - `TestCrossCollectionScope`: all four file endpoints (original/pdf/markdown/figures) return 404
    when `doc.collection_id != path collection_id` (IDOR guard).
- `tests/units/api/collections/documents/pages/test_pages.py` now covers:
  - `TestPagesCrossCollectionScope`: all four pages endpoints (list/detail/screenshot/reingest) return 404
    when `doc.collection_id != path collection_id` (same IDOR guard via `_require_document`).

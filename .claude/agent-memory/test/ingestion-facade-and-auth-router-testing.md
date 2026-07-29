---
name: ingestion-facade-and-auth-router-testing
description: Where IngestionFacade tests live and how to mock it; how to drive the real keys router + AuthBootstrap with auth forced ON in TestClient.
metadata:
  type: project
---

**IngestionFacade** (`shared/libs/services/db/facades/ingestion_facade.py`, the worker's write
path — `save`/`index`/`store_blobs`/`find_duplicate`) is tested in
`tests/units/worker/test_ingestion_facade.py`, NOT `tests/units/api/` (unlike
`test_filter_sync_facade.py`, which lives in `api/` by historical accident). It never imports
`backend.*`, so no fake-backend-module trick ([[bootstrap-mechanics]]) is needed — same direct
`_postgres_yielding`/monkeypatch-the-imported-name pattern as `test_filter_sync_facade.py` works
standalone. Key contracts proven: `save()` purges (`ChunkApi.delete_for_document` /
`IRApi.delete_for_document`) strictly BEFORE the matching re-insert, and sets
`DocumentStatus.DONE` last; `store_blobs()` writes S3 (`S3ObjectApi.put_many`) before the
Postgres registry (`BlobApi.register`); `index()` derives `semantic_fields`/`lexical_fields`/
`filterable_fields` from the collection's `MetadataField` schema (via `DatabaseHelpers`) and
calls `ChunkApi.mark_indexed` with `uuid.UUID(point.point_id)` for every upserted point. Schema
rows and ORM rows are plain `MagicMock(field_name=..., field_type=..., filterable=...)` —
no real SQLAlchemy instantiation needed for these facade tests.

**Driving the real keys router with auth ON** (`tests/units/api/test_auth_keys_router.py`): the
`client` fixture's `_auth_off_by_default` autouse fixture is overridden per-test with
`monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)`. Because `AuthMiddleware` (ASGI layer,
runs before FastAPI routing) calls `authenticate(request)` which hits
`CONTEXT.database.auth.get_key_with_user(hash)` for EVERY `/api/v1/*` call, that one method must
be mocked to return `(key, user)` for literally every request in the test, even ones only meant to
exercise the router body — a 403/401 test needs it to resolve to a REAL (non-full-access)
principal, not a missing one, or you get 401 from the middleware instead of 403 from
`AuthzGuard.enforce`. Prefer per-method `monkeypatch.setattr(CONTEXT.database.auth, "method",
AsyncMock(...))` over replacing the whole `CONTEXT.database` (test_enablement_routes.py's
convention) when going through a REAL TestClient request — other CONTEXT.database attributes may
be touched by the same request/middleware stack. Router calls mocked beyond
`get_key_with_user`: `get_user_by_username` (root resolution, 409 when None), `create_key`,
`list_keys`, `revoke_key`.

**AuthBootstrap.ensure_root_credential** (`app/backend/libs/auth/bootstrap.py`) is called directly
and `await`ed in the test — it only ever runs from `lifespan`, which TestClient does not execute.
Replacing the whole `CONTEXT.database` with `SimpleNamespace(auth=...)` is fine here (no real
HTTP request in flight, only the bootstrap classmethod itself runs) — same convention as
`test_auth.py`. Idempotency is two independent checks: `get_user_by_username` returning a row
skips `create_user`, and `get_key_by_hash` returning a row skips `create_key` — both must be
non-None to prove full no-op.

See also [[bootstrap-mechanics]] and [[auth-lot4-testing-patterns]].

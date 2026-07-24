---
name: auth-lot4-testing-patterns
description: How to unit-test the API-key auth gate (authenticate/AuthzGuard.enforce) without a real Starlette Request or DB, plus a validation-order trap in AuthzGuard.__parse.
metadata:
  type: project
---

`app/backend/libs/auth/{keys,dependency,authz,permissions}.py` (Lot 4) is fully testable with a
fake `Request`: both `authenticate` and `AuthzGuard.enforce` only ever touch
`request.headers.get(...)` and `request.path_params.get(...)`, so a
`SimpleNamespace(headers=dict, path_params=dict)` stands in — no real Starlette `Request`/scope
needed. Covered in `tests/units/api/test_auth.py`.

**Trap**: `AuthzGuard.enforce` calls `__parse` (which runs `KeyPermissions.model_validate` on the
WHOLE permissions blob) BEFORE it ever looks at `collection_id`. A test for "no `collection_id`
path param → scope check skipped" still needs a **fully valid** `collections` list (real UUIDs or
`["*"]`) in the fixture permissions blob — an invalid placeholder like `"some-other-id"` trips the
403-malformed-blob path first, never reaching the code path under test.

`AuthPrincipal` is a plain frozen dataclass — construct it directly for authz-only tests
(`AuthPrincipal(user=.., key=.., is_full_access=..)`), bypassing `from_key`, to control
`is_full_access` explicitly without needing a real `ApiKey`/`AppUser` ORM row (a `SimpleNamespace`
with just `.permissions`/`.revoked_at`/`.user_id` or `.is_active` is enough — same pattern as
[[bootstrap-mechanics]]'s SimpleNamespace-as-fake-row convention used throughout `tests/units/api/`).

`RUNTIME_CONFIG.AUTH_ENABLED` is a class attribute read at call time inside `authenticate` — safe
to `monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)` regardless of which module holds the
`from config import RUNTIME_CONFIG` reference (same class object everywhere).

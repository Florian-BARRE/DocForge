---
name: fixture-doubles-schema-drift
description: SimpleNamespace test doubles for ORM rows go stale when a table gains columns — fix the shared double factory, not just the failing test
metadata:
  type: feedback
---

`tests/units/api/test_auth.py` and `tests/units/api/test_auth_keys_router.py` build fake `ApiKey`/
`AppUser` rows with `types.SimpleNamespace` instead of the real SQLAlchemy model, so every field the
production code touches must be listed explicitly in the double. When `api_key` gained
`expires_at`/`last_used_at` columns, every hand-rolled `SimpleNamespace(...)` that didn't already list
them broke with `AttributeError` at the exact line of new code that reads the field — not just in the
"local" factory function but in EVERY inline `SimpleNamespace(...)` scattered across both test files
(the `_key()` helper in test_auth.py, `_root_principal_resolves`/`_scoped_non_admin_principal_resolves`
in test_auth_keys_router.py, and ad-hoc rows built inline for `list_keys`/`create_key` doubles).

**Why:** these files predate a shared key-double factory — there is no single choke point, so a new
nullable column requires grepping every `SimpleNamespace(` in the auth test files, not just editing one
helper.

**How to apply:** when a table gains a column, `grep -rn "SimpleNamespace(" tests/units/api/test_auth*.py`
and check each one against the model's current fields before assuming the shared `_key()`/`_user()`
helpers are the only place to fix. New nullable columns should default to `None` in the double
constructors so old call sites keep compiling.

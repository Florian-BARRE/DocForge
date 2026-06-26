---
name: auth-keys-only-capabilities
description: AUTH-A keys-only authz model — capability taxonomy, require_capability enforcement, the null=full-access footgun, and what NOT to flag
metadata:
  type: project
---

# Keys-only auth (AUTH-A, 2026-06-26)

Replaced multi-user/grants/impersonation with: single root account + permissioned API keys.
Per-collection authz is a JSONB `permissions` scope on `api_key`, NOT a DB grant lookup.

## How enforcement works (sanctioned — do NOT flag as missing)
- `backend/libs/auth/capabilities.py`: `Capability` StrEnum (documents.read/write, search,
  config.read/write, chunks.write, collection.admin) + read/write/admin shortcut expansion
  (read ⊂ write ⊂ admin). `CapabilityHelpers.grants(perms, cid, cap)` matches an entry whose
  collection_id == path id OR `"*"` wildcard AND whose expanded caps include the required cap.
- `require_capability(cap)` factory: reads `collection_id` from the path, gates collection-scoped
  routes. `require_capability_media(cap)` = same but header-OR-`?token=` for `<img>` media routes.
  SSE routes auth via `require_principal_sse` then call `principal_grants_capability(...)` in-body.
- Full-access bypass = `Principal.permissions is None` (`has_full_access`). The ONLY None paths:
  root password-JWT, static root env key, legacy null-permission key. This is the sole bypass — verified.
- Global routes (health/discovery/monitoring/jobs) use `require_principal` only (no collection_id) →
  no 500 on missing path param. By design: any valid key allowed.

## Cap↔route mapping (verified — none weaker than prior role)
ingest/update/reingest/delete-doc=documents.write; list/get/files/pages-read=documents.read;
chunk edit=chunks.write; config state/schema/history=config.read, update/rollback=config.write;
search=search; collection delete + limits GET&PUT=collection.admin. Shortcut expansion makes new
caps == old READ/WRITE/ADMIN. NOTE: limits **GET** moved READ→ADMIN (stricter, not a hole).

## Known footgun / risk (real, but documented + tested — flag as risk, not a bug)
- POST /auth/keys with `permissions` omitted → key gets `None` → **FULL ACCESS** (same sentinel as
  legacy back-compat). A forgotten scope fails OPEN, not closed. Tested intentional
  (`test_create_full_access_key_when_permissions_omitted`). Recommend explicit opt-in for full access.
- `POST /jobs/{id}/cancel` is destructive + cross-collection but gated only by `require_principal`
  (any valid key can cancel any job in any collection). NOT a regression — identical pre-AUTH-A —
  and design blesses jobs as global-allow. Recommend a documents.write check on the job's collection.

## Migration 015 (verified)
add `api_key.permissions` JSONB nullable + drop `collection_grant`; down_revision="014" (linear head),
reversible downgrade re-creates the 011 grant shape. Models: `ApiKeyModel.permissions`,
`AppUserModel` keeps only `api_keys` relationship (no grants). UserRole keeps ROOT+USER.

## Removals confirmed complete
No users/access routers, no CollectionGrant model/repo, no impersonation/Principal.impersonated_by.
Only app-code residue: stale docstring `app_user.py` line 4 ("...and per-collection grants"). 606 tests pass.

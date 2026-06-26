---
name: auth-keys-only-model
description: Keys-only authz (AUTH-A) — root account + permissioned API keys with per-collection capabilities; replaces the old grant/collaborator/impersonation model
metadata:
  type: project
---

AUTH-A (2026-06-26) pivoted authorization to ONE root account + permissioned API keys.

**Why:** the multi-user / collaborators / impersonation system was over-engineered for a single-operator
tool; the user wanted root-creates-scoped-keys (for MCP/scripts). Design doc:
`docs/rpi/auth-keys-only/design.md`.

**How to apply when touching auth:**
- Capability taxonomy is the SINGLE source of truth in `app/backend/libs/auth/capabilities.py`:
  `Capability` StrEnum (documents.read/write, search, config.read/write, chunks.write,
  collection.admin) + `PermissionRole` (read/write/admin/custom) + `CapabilityHelpers`
  (expand_entry / grants / validate_permissions). read⊂write⊂admin.
- Authorization pivot is `Principal.permissions` (`app/backend/libs/auth/models.py`): `None` =
  FULL access (root login JWT, static root env key, or a legacy NULL-permission DB key — back-compat);
  a dict = a scoped API key. `principal.has_full_access` == `permissions is None`.
- Collection-scoped routes use `require_capability(Capability.X)` / `require_capability_media(...)`
  (NOT the old `require_collection_role`). SSE/in-body checks use `principal_grants_capability(...)`.
- Route→capability map: documents list/get/files/pages/chunks-read/markdown → documents.read;
  ingest/update/reingest/delete + page reingest → documents.write; chunks update → chunks.write;
  search → search; config state/schema/history → config.read; config update/rollback → config.write;
  collection delete + limits(GET+PUT) → collection.admin. `/collections/list` is auth-only (not
  collection-scoped, so no capability gate — any valid principal).
- `POST /auth/keys` accepts optional `permissions` (validated via `CapabilityHelpers.validate_permissions`
  → 422 on malformed); GET `/auth/keys` + the create response echo `permissions`. Stored on
  `api_key.permissions` (JSONB nullable, migration 015).
- AuthService has NO grant_repo / effective_collection_role / impersonation anymore. `api_key.permissions`
  rides onto the Principal in `_resolve_api_key`.

**REMOVED (gone, do not resurrect):** `routers/users/`, `routers/collections/access/`,
`collection_grant` table + `CollectionGrantModel` + `CollectionGrantRepository`, `GrantRole` enum,
`Principal.impersonated_by`, `mint_impersonation_token`, `/auth/me` grants/impersonated_by.
The static frontend catch-all makes removed POST routes return 405 (method) not 404 — both mean
"route gone". MCP `users`/`access` tools (src/mcp) still reference removed endpoints → **mcp agent**
must drop them.

See [[verbose-error-handling-convention]] for the 403 message style.

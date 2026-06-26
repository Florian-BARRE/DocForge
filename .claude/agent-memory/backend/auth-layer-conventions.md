---
name: auth-layer-conventions
description: How the FastAPI auth layer is wired (Principal/JWT/AuthService) and the root impersonation (act-as) pattern
metadata:
  type: project
---

Auth layer lives in `app/backend/libs/auth/` (Principal, AuthService, TokenHelpers, PasswordHelpers, dependencies) + routers `auth/` (login/me/keys) and `users/` (root-only user mgmt). Repos are shared `common_libs.storage.postgres.repositories` (UserRepository, ApiKeyRepository, CollectionGrantRepository), accessed via `CONTEXT.{user_repo,api_key_repo,grant_repo,auth_service,postgres}`.

**Why:** auth is gated by `AUTH_ENABLED` (default false; currently true in the running stack). When false, `_authenticate` injects a synthetic nil-UUID root principal so the API behaves as pre-auth.

**How to apply:**
- Credential resolution order in `AuthService.resolve_principal`: static root key (constant-time) → JWT (`_resolve_jwt`, subject=user id) → DB API key (hash lookup). First match wins.
- `Principal` is `@dataclass(frozen=True, slots=True)`; carries `impersonated_by: uuid.UUID | None` (audit/display only — NEVER affects authorization, which is `global_role` + per-collection grants).
- **Impersonation (root act-as):** `POST /users/{id}/impersonate` (require_root) → `AuthService.mint_impersonation_token(target, impersonator_id)` mints a JWT with subject=TARGET id + extra claims `role`/`impersonated_by`. The token resolves natively to the target principal, so every personal endpoint (/auth/keys, /auth/me, /collections/{id}/access) operates AS the target with the target's exact permissions — no per-endpoint duplication. Standard `AUTH_JWT_TTL_MINUTES` TTL. `TokenHelpers.mint` takes optional `extra_claims` that can NEVER override reserved sub/iat/exp. `/auth/me` surfaces `impersonated_by` for the UI "Acting as" banner. This unblocks UI-5 (account menu / per-collection Access / root Admin Act-as).
- **On-behalf admin (no impersonation needed):** root manages a SPECIFIC user's keys/grants directly via `users/` routes (all require_root, under `/users/{user_id}`): `GET/POST /keys`, `DELETE /keys/{key_id}`, `GET /grants`. They REUSE `api_key_repo.create/list_for_user/revoke` (already user_id-parameterized) + `auth_service.generate_api_key` (never reimplement crypto) targeting a different user_id than the caller; key responses reuse auth router's `ApiKey*` models. `revoke(session, key_id, user_id)` is owner-scoped → 404 covers unknown/foreign/already-revoked. Create-key: 404 unknown user, 409 inactive (dead key). `GET /grants` uses NEW `CollectionGrantRepository.list_by_user(user_id)` (full rows, counterpart to `list_for_collection`) + resolves `collection_name` per grant via `collection_repo.get_by_id`. Grant MUTATION stays on `PUT/DELETE /collections/{cid}/access/{user_id}` (admin-gated) — on-behalf only adds the read aggregate. Shared `_load_user_or_404` helper guards all four. Unblocks the frontend per-user management panel.
- User deletion is SOFT (set_active=False); there is no hard-delete endpoint. Root cannot self-deactivate (409).
- Verbose-error convention applies: log every rejection + use precise HTTP codes (impersonate: 404 unknown, 409 inactive); tests assert each code. API tests mock CONTEXT (`tests/units/api/conftest.py`) with an `authed_client` fixture that flips AUTH_ENABLED=true and programs `mock_auth_service`.

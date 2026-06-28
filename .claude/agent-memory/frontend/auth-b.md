---
name: auth-b
description: AUTH-B simplified root-only auth — AuthContext, API keys, shell/nav, AppShell, prop threading
metadata:
  type: project
---

## Auth integration (AUTH-B — current model)

Supersedes [[ui5-auth-admin-scoping]] (multi-user + impersonation removed in AUTH-B).

**Single root login only.** No multi-user, no impersonation, no per-collection grants.

- `src/auth/AuthContext.tsx` — `{token, user, loading, login(), logout()}`. Token in `localStorage`
  key `docforge.auth.token`. On mount: calls `/auth/me`; 401 → force-logout.
  Registers token with `api/client.ts` via `setAuthToken()`.
- `src/auth/LoginScreen.tsx` — full-screen login, renders when `user === null`.
- `src/auth/permissions.ts` — `canWrite(user: UserSummary | null): boolean` only (root check).
- `api/client.ts`: module-level `_bearerToken` + `_onUnauthorized`. **401 → force-logout. 403 → Error.**
  `createApiKey(name, permissions)` — `permissions` is REQUIRED. `listApiKeys()` returns keys with
  `permissions: Permissions | null`.
- **Removed from api/client.ts in AUTH-B**: createUser, listUsers, deleteUser, resetUserPassword,
  impersonateUser, listCollectionAccess, setCollectionAccess, revokeCollectionAccess.
- **api/types.ts removed**: `CollectionGrantSummary`, `UserResponse`, `UserListResponse`,
  `DeactivateUserResponse`, `ImpersonateResponse`, `AccessGrantResponse`, `AccessListResponse`.
  `MeResponse` is now `{user: UserSummary}` (no grants).
- **api/types.ts added**: `Capability`, `PermissionRole`, `PermissionEntry`, `Permissions`.
- **Dead stubs** (`export {}`): `components/admin/AdminView.tsx`, `UsersPanel.tsx`,
  `CollectionAccessPanel.tsx`, `ApiKeysPanel.tsx`, `layout/ImpersonationBanner.tsx`.
- SSE EventSource token: `?token=` query param (no header support).
- `main.tsx` wraps `<App>` in `<AuthProvider>`.

## API Keys page

- `components/apikeys/ApiKeysPage.tsx` — orchestrator (loads keys + collections, composes sub-components).
- `components/apikeys/CreateKeyForm.tsx` — name input + PermissionBuilder + submit.
- `components/apikeys/PermissionBuilder.tsx` — all-collections vs specific toggle; `PermissionRowDraft[]`
  state; emits `Permissions` via onChange; counter-based stable local IDs.
- `components/apikeys/PermissionEntryRow.tsx` — collection select + RoleChipGroup + "Advanced" expander.
- `components/apikeys/RoleChipGroup.tsx` — chip-style read/write/admin selector.
- `components/apikeys/CapabilityCheckboxes.tsx` — 7-item capability checkbox grid.
- `components/apikeys/KeyRevealCallout.tsx` — one-time plaintext key reveal + copy + dismiss.
- `components/apikeys/ApiKeysList.tsx` — DataTable of ApiKeySummary rows with revoke button.
- `components/apikeys/apiKeyTypes.ts` — `CAPABILITY_LABELS`, `ALL_CAPABILITIES`, `ROLE_CAPABILITIES`,
  `PermissionRowDraft`, `formatScopeSummary()`.
  Scope shortcuts: read={documents.read,search,config.read}; write=read+{documents.write,config.write,
  chunks.write}; admin=write+{collection.admin}.

## Shell/nav (AUTH-B)

- `NavRail.tsx` GlobalView: `'pipeline'|'documents'|'search'|'observability'|'apikeys'`.
  `showApiKeys` prop (was `showAdmin`). Label "API Keys", icon "🔑".
- `ContextBar.tsx` CollectionTab: `'pipeline'|'documents'|'search'` ("access" removed).
  `isCollectionAdmin` prop removed. `VIEW_LABEL` has `'apikeys': 'API Keys'`.
- `AccountMenu.tsx` — dropdown with "Sign out" only (API Keys drawer removed).
- `AppShell.tsx` — no grants/impersonation/ImpersonationBanner/AdminView/CollectionAccessPanel.
  `write = canWrite(user)`. Renders `<ApiKeysPage />` when `activeView === 'apikeys'`.
  `showApiKeys = user.role === 'root'`.

## Role-based UI prop threading

Pattern: permissions computed ONCE at AppShell, threaded as props — no `useAuth()` in deep components.
- `AppShell` → `canWrite` prop → `DocumentsTab` (drop-zone, file input, re-index, `DocRow.canWrite`)
  and `PipelineTab` → `StageConfigPanel` → `ConfigSaveBar` / `IngestionConditionsPanel`.
- `ConfigHistoryPanel`: rollback buttons gated on `canWrite`.
- `DocRow`: inline reingest + overflow menu (Re-ingest / Delete) gated on `canWrite`.
- `AuthProvider` sets `loading=true` until `/auth/me` resolves — `App.tsx` shows blank (no flash).

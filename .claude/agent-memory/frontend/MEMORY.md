# Frontend Craftsman — Memory Index

`src/docforge/app/frontend/` — React 18 + Vite + TypeScript, served as static `dist/` by FastAPI.

## Rules (general.md + fastapi.md frontend section)

- Theme tokens in `src/theme.ts` (dark-first: base `#0d0f18`, indigo accent `#6366f1`) — NO hardcoded
  colors anywhere else. No external UI library.
- One component per file, grouped by feature (`components/<feature>/X.tsx`), small + single-purpose.
- English everywhere; object-oriented, component-based.

## Architecture invariants (do not regress)

- **Forms are never hand-coded per endpoint.** Primitives: `<RequestForm endpoint= discovery=>`
  (static body + query + root overlays) and `<DynamicFieldsGroup fields= prefix=>` (nested overlays).
  Canonical consumers: CollectionStep, ConfigStep, IngestStep, SearchView, BrowseView. A new view that
  hits an endpoint with a body/query MUST go through RequestForm so a new backend Pydantic field
  surfaces automatically.
- Dynamic field kinds: `MultiPicker` (chain `kind="multi"`), `ScalarPicker` (`kind="scalar"`),
  `ChoicePicker`. The `DynamicFieldKind` enum in `types.ts` must match the backend discovery overlay.
- `api/client.ts` = typed client; `api/generated.ts` = OpenAPI client, **regenerate** with
  `npm run gen:types` (never hand-edit; stale generated.ts breaks `tsc`). `tsconfig` has `noEmit: true`.
- SSE: `EventSource` (native auto-reconnect), debounced refetch, polling fallback torn down once events
  resume (see DocumentsTab).

## Auth integration (AUTH-B — simplified root-only model)

- **Single root login only.** No multi-user, no impersonation, no per-collection grants.
- `src/auth/AuthContext.tsx` — provider holding `{token, user, loading, login(), logout()}`.
  Token persisted in `localStorage` under key `docforge.auth.token`. On mount: calls `/auth/me` to
  rehydrate; 401 → force-logout. Registers the token with `api/client.ts` via `setAuthToken()`.
  **Removed in AUTH-B**: `grants`, `isImpersonating`, `impersonatedUser`, `actAs`, `exitImpersonation`.
- `src/auth/LoginScreen.tsx` — full-screen login form, renders when `user` is null.
- `src/auth/permissions.ts` — `canWrite(user: UserSummary | null): boolean` only (root check).
  `getCollectionRole`, `canRead`, `canAdmin` removed. No `CollectionGrantSummary`.
- `api/client.ts` auth pattern: module-level `_bearerToken` + `_onUnauthorized`.
  **401 → force-logout. 403 → surface as normal Error.**
  **Removed in AUTH-B**: `createUser`, `listUsers`, `deleteUser`, `resetUserPassword`,
  `impersonateUser`, `listCollectionAccess`, `setCollectionAccess`, `revokeCollectionAccess`.
- **`createApiKey(name, permissions)` — permissions is now REQUIRED** (no longer optional).
  `listApiKeys()` returns keys with `permissions: Permissions | null`.
- `api/types.ts` removed types: `CollectionGrantSummary`, `UserResponse`, `UserListResponse`,
  `DeactivateUserResponse`, `ImpersonateResponse`, `AccessGrantResponse`, `AccessListResponse`,
  `RevokeAccessResponse`. `MeResponse` is now `{user: UserSummary}` (no grants field).
- **New in AUTH-B** (`api/types.ts`): `Capability`, `PermissionRole`, `PermissionEntry`, `Permissions`.
- **Dead files (stubbed `export {}`)**: `components/admin/AdminView.tsx`, `UsersPanel.tsx`,
  `CollectionAccessPanel.tsx`, `ApiKeysPanel.tsx`, `layout/ImpersonationBanner.tsx`.
- SSE `EventSource` token passed as `?token=` query param (no header support).
- `main.tsx` wraps `<App>` in `<AuthProvider>`.

## API Keys page (AUTH-B)

- `components/apikeys/ApiKeysPage.tsx` — orchestrator: loads keys + collections on mount, composes
  CreateKeyForm + KeyRevealCallout + ApiKeysList. Handles `onCreated` (appends to list in-place) and
  `onRevoked` (marks revoked_at in-place).
- `components/apikeys/CreateKeyForm.tsx` — name input + PermissionBuilder + submit.
- `components/apikeys/PermissionBuilder.tsx` — all-collections vs specific toggle. Manages
  `PermissionRowDraft[]` state; emits `Permissions` via onChange on every change. Counter-based
  stable local IDs for row reconciliation.
- `components/apikeys/PermissionEntryRow.tsx` — one scope row: collection `<select>` + RoleChipGroup
  + "Advanced" expander (switches to CapabilityCheckboxes + role='custom').
- `components/apikeys/RoleChipGroup.tsx` — chip-style read/write/admin role selector (controlled).
- `components/apikeys/CapabilityCheckboxes.tsx` — 7-item capability checkbox grid.
- `components/apikeys/KeyRevealCallout.tsx` — one-time plaintext key reveal with copy button +
  dismiss. Parent renders it conditionally; after dismiss, `createdKey` state → null.
- `components/apikeys/ApiKeysList.tsx` — DataTable of ApiKeySummary: name/prefix, scope summary,
  created, last used, status tag (active/revoked), revoke button.
- `components/apikeys/apiKeyTypes.ts` — `CAPABILITY_LABELS`, `ALL_CAPABILITIES`, `ROLE_CAPABILITIES`,
  `PermissionRowDraft` interface, `formatScopeSummary()`.
- **Scope shortcuts** (hardcoded in apiKeyTypes.ts): read={documents.read,search,config.read};
  write=read+{documents.write,config.write,chunks.write}; admin=write+{collection.admin}.

## Shell/nav (AUTH-B)

- `GlobalView` in NavRail.tsx: `'pipeline'|'documents'|'search'|'observability'|'apikeys'`
  (renamed from 'admin'). Prop renamed `showApiKeys` (was `showAdmin`). Label: "API Keys", icon "🔑".
- `CollectionTab` in ContextBar.tsx: `'pipeline'|'documents'|'search'` — "access" tab removed.
  `isCollectionAdmin` prop removed. `VIEW_LABEL` includes `'apikeys': 'API Keys'`.
- `AccountMenu.tsx` simplified: API Keys drawer removed. Dropdown has only "Sign out".
- `AppShell.tsx`: no `grants`, no `isImpersonating`, no `ImpersonationBanner`, no `AdminView`,
  no `CollectionAccessPanel`. `write = canWrite(user)` (root role check). Renders `<ApiKeysPage />`
  when `activeView === 'apikeys'`. `showApiKeys = user.role === 'root'`.

## Role-based UI prop threading

- `AppShell.tsx` computes `write = canWrite(user)` and threads as `canWrite` prop to
  `DocumentsTab` and `PipelineTab`. Components accept `canWrite?: boolean` (default true).
- `DocumentsTab`: drop-zone, file input, metadata form, re-index button, `DocRow.canWrite`
- `DocRow`: inline reingest (stale) + overflow menu (Re-ingest / Delete)
- `PipelineTab` → `StageConfigPanel` → `ConfigSaveBar` / `IngestionConditionsPanel`
- `ConfigHistoryPanel`: rollback buttons
- Pattern: permissions derived once at AppShell, threaded as props — no `useAuth()` in deep components.
- Loading state: `AuthProvider` sets `loading=true` until `/auth/me` resolves — `App.tsx` renders
  blank screen (no login flash).

## Document detail view — tab layout

`DocDetailView.tsx` is the orchestrator; each tab is its own file under `components/documents/detail/`:
- `OverviewTab` / `IRTab` / `ChunksTab` / `PagesTab` / `DownloadsTab` — pre-existing
- `ChainTracesTab` — renders `chain_traces` (parse/S1) and `embed_chain_traces` (S6) via `<ChainTraceView>`
- `JobsTab` — renders `doc.jobs[]` newest-first with expandable error rows

`<ChainTraceView>` accepts `traces: ChainTrace[]` and `variant: 'compact' | 'detailed'`.
CSS classes for the jobs list live in `global.css` under `/* ── Jobs Tab ──... */`.

## Boundary

UI code only. REST contract changes → **backend** agent. Build/serve of `dist/` → **docforge** agent.
Adding a backend Pydantic field IS a UI feature (no separate ticket) — verify via `/discovery` reload.

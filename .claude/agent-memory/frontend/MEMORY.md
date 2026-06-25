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

## Auth integration (P9)

- `src/auth/AuthContext.tsx` — provider holding `{token, user, grants, loading, login(), logout()}`.
  Token persisted in `localStorage` under key `docforge.auth.token`. On mount: calls `/auth/me` to
  rehydrate; 401 → force-logout. Registers the token with `api/client.ts` via `setAuthToken()`.
- `src/auth/LoginScreen.tsx` — full-screen login form, renders when `user` is null.
- `src/auth/permissions.ts` — `getCollectionRole / canRead / canWrite / canAdmin` helpers.
- `api/client.ts` auth pattern: module-level `_bearerToken` + `_onUnauthorized` (registered by
  AuthContext). Every `request()` and `upload()` reads `_bearerToken` via `authHeaders()`.
  **401 → force-logout (onUnauthorized callback). 403 → surface as a normal Error, no logout.**
- SSE `EventSource` cannot send headers: token passed as `?token=` query param. Backend may need to
  accept this for SSE endpoints (follow-up with backend agent if SSE breaks after auth).
- Auth types are hand-written in `api/types.ts` (not generated) because the auth router was added
  after the last `npm run gen:types`. Regenerate `generated.ts` to absorb them when possible.
- Admin area: `components/admin/AdminView.tsx` (tabs) + `UsersPanel.tsx` (root-only) +
  `ApiKeysPanel.tsx` (any user) + `CollectionAccessPanel.tsx` (root or collection admin).
  Gated in `App.tsx` by `user.role === 'root'` for the Users tab; `canAdmin()` for Collaborators.
- **Role-based UI prop threading**: `App.tsx` computes `write = canWrite(user, grants, activeCollectionId)`
  from `useAuth()` + `permissions.ts`, then passes it as `canWrite` prop to `DocumentsTab` and
  `PipelineTab`. Components accept `canWrite?: boolean` (default true) and gate:
  - `DocumentsTab`: drop-zone, hidden file input, metadata form, "Tout réindexer" button, `DocRow.canWrite`
  - `DocRow`: inline reingest (stale) + overflow menu (Re-ingest / Delete)
  - `PipelineTab` → `StageConfigPanel` → `ConfigSaveBar` / `IngestionConditionsPanel` (all inputs + save bar)
  - `ConfigHistoryPanel`: rollback "Restaurer" buttons
  - Pattern: permissions are derived once at `App.tsx` and threaded as props — never call `useAuth()` deep
    in a component tree. This keeps permission logic central and the component tree testable.
- Loading state: `AuthProvider` sets `loading=true` until `/auth/me` resolves — `App.tsx` renders a
  blank loading screen instead of the login screen flash.
- `main.tsx` wraps `<App>` in `<AuthProvider>`.

## Document detail view — tab layout

`DocDetailView.tsx` is the orchestrator; each tab is its own file under `components/documents/detail/`:
- `OverviewTab` / `IRTab` / `ChunksTab` / `PagesTab` / `DownloadsTab` — pre-existing
- `ChainTracesTab` — renders `chain_traces` (parse/S1) and `embed_chain_traces` (S6) via `<ChainTraceView>`
- `JobsTab` — renders `doc.jobs[]` newest-first with expandable error rows

`types.ts` hand-written overlays (added after last gen):
- `JobResponse` + `JobStatus` — mirrors backend JobResponse exactly
- `Document` extended with `jobs?: JobResponse[]`
- `chain_traces` / `embed_chain_traces` already in generated `DocumentResponse`

`<ChainTraceView>` (inspect feature) is the canonical chain-of-fallbacks renderer — always reuse it,
never write a new renderer. It accepts `traces: ChainTrace[]` and `variant: 'compact' | 'detailed'`.

CSS classes for the jobs list live in `global.css` under `/* ── Jobs Tab ──... */`.

## Boundary

UI code only. REST contract changes → **backend** agent. Build/serve of `dist/` → **docforge** agent.
Adding a backend Pydantic field IS a UI feature (no separate ticket) — verify via `/discovery` reload.

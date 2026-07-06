# Frontend Craftsman — Memory Index

Two frontend trees exist. **`src/docforge-rework/app/frontend/`** is the active clean-slate
rewrite — most new work should land there. `src/docforge/app/frontend/` is the legacy v1 product.
Their conventions differ in places (see below) — don't apply one tree's rule to the other blindly.

## Core rules — legacy (`src/docforge/app/frontend/`)

- Theme tokens from `src/theme.ts` only (dark-first: base `#0d0f18`, indigo accent `#6366f1`) — no hardcoded colors, no external UI library.
- One component per file, grouped by feature (`components/<feature>/X.tsx`), small + single-purpose. English everywhere.
- **Forms never hand-coded per endpoint** — use `<RequestForm endpoint= discovery=>` + `<DynamicFieldsGroup fields= prefix=>` (discovery-driven); new backend Pydantic fields surface automatically via `/discovery` reload.
- `api/generated.ts` = OpenAPI types — **regenerate with `npm run gen:types`**, never hand-edit (stale file breaks `tsc`). `tsconfig` has `noEmit: true`.
- Dynamic field kinds: `MultiPicker` (`kind="multi"`), `ScalarPicker` (`kind="scalar"`), `ChoicePicker`. `DynamicFieldKind` enum in `types.ts` must match backend discovery overlay.
- SSE via native `EventSource` (auto-reconnect); polling fallback torn down once events resume. Token passed as `?token=` query param.

## Core rules — rework (`src/docforge-rework/app/frontend/`)

- Hand-rolled routing, no router dependency: `shell/view.ts` defines `View` as one discriminated
  union; `App.tsx` is the ONLY file that switches on `view.name`; every page takes its view's
  params + a single `onNavigate: Navigate` prop.
- No `RequestForm`/`DynamicFieldsGroup`/`generated.ts`/`gen:types` here — that legacy discovery-driven
  primitive set was not carried over (confirmed absent as of 2026-07-05). `api/<feature>.ts` files
  hand-mirror the backend Pydantic models verbatim (own comment says so) behind a typed client —
  no OpenAPI codegen step exists yet in this tree.
- Two different "generic form" mechanisms coexist here — don't conflate them:
  - `features/pipeline-editor/inspector/SchemaForm.tsx` + `SchemaField.tsx` — genuinely JSON-Schema
    driven, renders any node's `config_schema` from the describe/palette API. Reused as-is by
    `features/stage-rail/` (import path stays `../pipeline-editor/inspector/SchemaForm`).
  - `features/collections/wizard/*` — a bespoke hand-built multi-step domain wizard (identity →
    schema → review). Intentionally NOT generic: collection create/edit is a multi-step UX with
    its own validation, not a single-endpoint form. See [[collection-edit-wizard]].
- **Pipeline UI = two studios, one routed.** `features/stage-rail/` (vertical fixed-shape rail) is
  the DEFAULT since 2026-07-02, embedded by `CollectionPipelinePage`. `features/pipeline-editor/`
  (the react-flow canvas) is UNROUTED but still in the tree for a future advanced mode — don't
  delete it, don't wire it back without being asked. See [[stage-rail]].
- Theme tokens (`src/theme.ts`) differ from the legacy palette: base `#0f1115`, blue accent
  `#4f8cff` (legacy is indigo `#6366f1`). Same "tokens only, no hardcoded colors" rule applies.
- Page remount = free refetch: pages render behind `{view.name === "x" && <Page/>}` conditionals in
  `App.tsx`, so navigating away and back always unmounts/remounts the page component —
  `useEffect(load, [id])` on mount is enough to guarantee fresh data, no manual cache invalidation
  needed after a mutation. See [[collection-edit-wizard]].

## Topic files — rework

- [Collection edit wizard (dual-mode form)](collection-edit-wizard.md) — `CollectionWizard` mode="create"|"edit" + initial prefill; fetch-wrapper page pattern; needs_reindex banner
- [Stage rail (fixed-shape pipeline UI)](stage-rail.md) — replaced the canvas editor as default; `stages/view`+`stages/apply` contract; generic config-schema resolution; chain accent token
- [Document explorer](document-explorer.md) — collection→documents→document tabs; page-level lazy per-tab fetch cache; cross-tab jump-to-block via always-mounted+CSS-hidden rows; 0-based page numbering gotcha

## Topic files — legacy

- [Auth / API Keys / Shell / Permissions threading (AUTH-B)](auth-b.md) — root-only login, JWT, `canWrite` prop threading, NavRail, AppShell; supersedes [[ui5-auth-admin-scoping]]
- [Document detail view + ValueRenderer + OverviewTab (UI-3)](detail-view.md) — tab layout, ValueRenderer classification rules, OverviewTab sections, `consumed` set gotchas, SectionBlock null-guard fix
- [Search Lab (UI-2)](search-lab.md) — LabTuningPanel, LabDebugPanel, `useLabOverrides`, `HttpError`, vector names, overrides wiring
- [Pipeline canvas — react-flow (R2)](react-flow-canvas.md) — `@xyflow/react` v12, `PipelineCanvas`, `StageFlowNode`, token theming, dead stubs
- [UX consistency batch 3 (UX-B3)](ux-b3.md) — ConfirmDialog primitive, Spinner/EmptyState standardization, window.confirm→0
- [ObjectListPicker pattern](object-list-picker.md) — generic object_list repeater; item-local read/write via last-segment extraction (mirrors ChainLadder.writeEntryParam)
- [S5b metagen UI wiring](s5b-metagen-ui.md) — origin overlay on MetaField, object_list ConfigNode, MetagenPreview, warning-banner CSS, s5b stage definition
- [gen:types cannot run without backend](gen-types-constraint.md) — use overlay intersections in types.ts; never hand-edit generated.ts

## Boundary

UI code only. REST contract changes → **backend** agent. Build/serve of `dist/` → **docforge** agent.
Adding a backend Pydantic field IS a UI feature (no separate ticket) — verify via `/discovery`
(legacy) or a page reload against the live backend (rework, no discovery endpoint there).

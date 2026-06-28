# Frontend Craftsman — Memory Index

`src/docforge/app/frontend/` — React 18 + Vite + TypeScript, served as static `dist/` by FastAPI.

## Core rules

- Theme tokens from `src/theme.ts` only (dark-first: base `#0d0f18`, indigo accent `#6366f1`) — no hardcoded colors, no external UI library.
- One component per file, grouped by feature (`components/<feature>/X.tsx`), small + single-purpose. English everywhere.
- **Forms never hand-coded per endpoint** — use `<RequestForm endpoint= discovery=>` + `<DynamicFieldsGroup fields= prefix=>` (discovery-driven); new backend Pydantic fields surface automatically via `/discovery` reload.
- `api/generated.ts` = OpenAPI types — **regenerate with `npm run gen:types`**, never hand-edit (stale file breaks `tsc`). `tsconfig` has `noEmit: true`.
- Dynamic field kinds: `MultiPicker` (`kind="multi"`), `ScalarPicker` (`kind="scalar"`), `ChoicePicker`. `DynamicFieldKind` enum in `types.ts` must match backend discovery overlay.
- SSE via native `EventSource` (auto-reconnect); polling fallback torn down once events resume. Token passed as `?token=` query param.

## Topic files

- [Auth / API Keys / Shell / Permissions threading (AUTH-B)](auth-b.md) — root-only login, JWT, `canWrite` prop threading, NavRail, AppShell; supersedes [[ui5-auth-admin-scoping]]
- [Document detail view + ValueRenderer + OverviewTab (UI-3)](detail-view.md) — tab layout, ValueRenderer classification rules, OverviewTab sections, `consumed` set gotchas, SectionBlock null-guard fix
- [Search Lab (UI-2)](search-lab.md) — LabTuningPanel, LabDebugPanel, `useLabOverrides`, `HttpError`, vector names, overrides wiring
- [Pipeline canvas — react-flow (R2)](react-flow-canvas.md) — `@xyflow/react` v12, `PipelineCanvas`, `StageFlowNode`, token theming, dead stubs
- [UX consistency batch 3 (UX-B3)](ux-b3.md) — ConfirmDialog primitive, Spinner/EmptyState standardization, window.confirm→0

## Boundary

UI code only. REST contract changes → **backend** agent. Build/serve of `dist/` → **docforge** agent.
Adding a backend Pydantic field IS a UI feature (no separate ticket) — verify via `/discovery` reload.

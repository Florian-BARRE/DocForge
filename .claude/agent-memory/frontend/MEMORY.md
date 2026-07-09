# Frontend Craftsman — Memory Index

The React UI of the ACTIVE product: **`src/docforge-rework/app/frontend/`** (being renamed `docforge`).
The legacy `src/docforge/app/frontend/` is FROZEN — don't apply its conventions here.

## Core rules (rework)

- **Hand-rolled routing, no router dependency:** `shell/view.ts` defines `View` as one discriminated
  union; `App.tsx` is the ONLY file that switches on `view.name`; every page takes its view's params +
  a single `onNavigate: Navigate` prop. See [[shell-hand-rolled-routing]].
- **Page remount = free refetch:** pages render behind `{view.name === "x" && <Page/>}` in `App.tsx`,
  so navigating away/back unmounts + remounts — `useEffect(load, [id])` on mount guarantees fresh data,
  no manual cache invalidation after a mutation.
- **Theme tokens only** (`src/theme.ts`): base `#0f1115`, blue accent `#4f8cff`. No hardcoded colors,
  no external UI library. One component per file, grouped by feature, small + single-purpose, English.
- **Two "generic form" mechanisms coexist — don't conflate:**
  - `features/pipeline-editor/inspector/SchemaForm.tsx` (+ `SchemaField.tsx`) — genuinely JSON-Schema
    driven, renders any node's `config_schema` from the describe/palette API. Reused as-is by
    `features/stage-rail/`.
  - `features/collections/wizard/*` — a bespoke hand-built multi-step domain wizard (identity → schema
    → review). Intentionally NOT generic. See [[collection-edit-wizard]].
- **Pipeline UI = two studios, one routed.** `features/stage-rail/` (vertical fixed-shape rail) is the
  DEFAULT (since 2026-07-02), embedded by `CollectionPipelinePage`. `features/pipeline-editor/` (the
  react-flow canvas) is UNROUTED but kept for a future advanced mode — don't delete or rewire it
  unasked. Pipeline edits are server-owned (`POST /edit`), not client-side blob mutation. See
  [[stage-rail]], [[pipeline-editor-server-owned-edit]].
- **API types:** `api/<feature>.ts` files hand-mirror the backend Pydantic models behind a typed
  client. `npm run gen:types` codegen needs a LIVE backend at `OPENAPI_URL`; for new backend fields
  without one, use overlay intersections in `types.ts` — see [[gen-types-constraint]].

## Topic files

- [Shell hand-rolled routing](shell-hand-rolled-routing.md) — the navigation pattern: a discriminated View union + useState, no router dependency.
- [Stage rail](stage-rail.md) — vertical fixed-shape pipeline UI; replaced the canvas as default; `stages/view`+`stages/apply` contract; fallback chains = the chain-accent primitive.
- [Pipeline editor — server-owned edit](pipeline-editor-server-owned-edit.md) — migrated from client-side blob mutation to server-owned `POST /edit`; the one deliberate exception (typing debounce).
- [Collection edit wizard](collection-edit-wizard.md) — `CollectionWizard` reused in edit mode (mode/initial props) to PATCH collections; fetch-wrapper page pattern for prefilling a dual-mode form.
- [Document explorer](document-explorer.md) — collection→documents→document tabs; per-tab lazy fetch cached at the page level; cross-tab jump-to-block.
- [Auth (AUTH-B)](auth-b.md) — simplified root-only auth: AuthContext, API keys, shell/nav, AppShell, prop threading.
- [gen:types constraint](gen-types-constraint.md) — `npm run gen:types` requires a running backend at `OPENAPI_URL`; use overlay intersections in `types.ts` for new backend fields.
- [Backend enum gotchas](backend-enum-gotchas.md) — two backend enum surprises found building the collections/monitoring UI; verify before trusting a "queued"/enum assumption.
- [Collection model created_at gap](collection-model-created-at-gap.md) — `CollectionModel` (API) omits `created_at` though the DB row has it — hand to backend before adding a "created" column.
- [Empty-group blob validates](empty-group-blob-validates.md) — an empty pipeline group is NOT a valid 422 case; the validator skips the entry-node check when there are no children.

## Boundary

UI code only. REST contract changes → **backend** agent. Build/serve of `dist/` → **docforge** agent.
Adding a backend Pydantic field IS a UI feature (no separate ticket) — verify against the live backend.
- [Stage-rail chain contract](stage_rail_chain_contract.md) — set_chain slot=null rule, the contextualize llm nested chain, scored-vs-failure-only threshold gating

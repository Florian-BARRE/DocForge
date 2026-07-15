---
name: search-pipeline
description: The search pipeline editor (collection.search) — its own studio, NOT the stage rail; no stage compiler exists for search so it drives /inspect directly; the {} sentinel and the collection-search view-name trap.
metadata:
  type: project
---

Shipped 2026-07-15 in `src/docforge-rework/app/frontend/src/features/search-pipeline/` +
`features/collections/CollectionSearchPage.tsx`, mirroring `features/stage-rail/` +
`CollectionPipelinePage.tsx` for the SEARCH pipeline (`collection.search`, distinct from
`collection.pipeline`). Routed as view `collection-search-pipeline` (button "Edit search
pipeline" on `CollectionDetailPage`).

**Naming trap: `"collection-search"` was already taken.** It routes to `features/search/
SearchLabPage.tsx` — the query-testing lab (run a search, inspect hits), NOT a pipeline editor.
Before adding any new "search"-flavoured view, `grep shell/view.ts` first — the obvious name is
usually already claimed by something else in this codebase.

**Why this is NOT just "StageRailPage for a different key".** `listPipelineDesigns()`'s search
descriptor has `stages_view_url: null` / `stages_apply_url: null` — the backend's `StageCompiler`/
`StageViewer` only exist for `ingest` (`shared/libs/pipelines/ingest/stages/`). Search has no
canonical fixed-stage skeleton — it's a flat, fixed-topology `GroupBlob` (5 `ActionBlob` nodes:
`query/normalize → encode/collection → retrieve/hybrid → postprocess/hydrate → deliver/hits`,
already in run order in `blob.nodes`). Consequences for the editor:
- No `/apply` round-trip that recompiles server-side — every config edit is a plain **local**
  immutable replace of one node's `config` in the blob (`state/blobOps.ts::setNodeConfigField`).
  This does NOT contradict `[[pipeline-editor-server-owned-edit]]` (that rule is about *structural*
  edits on the canvas editor) — here there is no structural edit surface at all, only config values
  on a topology the backend has already fixed.
  Only 2 of the 5 nodes carry config (`query/normalize`: `fold_case`/`candidate_multiplier`/
  `candidate_floor`; `retrieve/hybrid`: `rescore_pool_size`); the other 3 render as read-only cards
  (name + summary only) via `hasConfigFields(findNodeCard(...))`.
- No validity comes for free (no `/stages/view` to fold it in) — the editor calls `POST
  {inspect_url}` itself, once on load and then debounced (400ms, same constant as the stage rail)
  after every keystroke, using an `AbortController` per call so a stale response can't clobber a
  newer one (`if (blobLatestRef.current !== target) return`).

**The `{}` sentinel is load-bearing — "Reset to default" must PATCH `{}`, never the expanded
blob.** Every collection's `search` is `{}` today (verified live across 22 collections), meaning
"track whatever the stock default graph is". Saving the *expanded* default blob instead would look
identical right now but freezes the collection against future stock-default changes — a real
regression a naive "reset = load default into the form" implementation would introduce silently.
So `SearchPipelineEditor`'s `onResetToDefault` prop is a distinct callback from `onSave` (the page
implements it as `updateCollection(id, {search: {}})`), and the page forces a remount afterward
(`key={resetVersion}`, bumped post-reset) so the editor re-seeds from the now-sentinel-backed
collection and displays the expanded default again — a "page remount = free refetch" variant
scoped to one child component instead of a whole page.

**`paletteLookup.ts` relocated: `features/stage-rail/state/` → `components/schema-form/
paletteLookup.ts`.** It was always feature-agnostic (pure `Palette`/`NodeCard` lookups by
`(family, kind)` — no `StageView` coupling), just misplaced by folder. Moved so both the stage rail
AND `features/search-pipeline/NodeConfigForm.tsx` share one resolver; all 8 stage-rail importers
updated, ingestion rail re-verified via the TS gate after the move. `features/stage-rail/state/`
still exists (`stageOps.ts` remains, genuinely stage-rail-specific).

**Correction to a stale memory claim**: `features/pipeline-editor/` (the react-flow canvas studio)
no longer exists in the tree as of this session — `find`/`git log` both come up empty for that
path. [[stage-rail]] and the MEMORY.md core-rules bullet describing it as "UNROUTED but kept" are
now WRONG; treat any future reference to a canvas pipeline editor as needing re-verification, not
as a standing fact.

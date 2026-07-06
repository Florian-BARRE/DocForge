---
name: stage-rail
description: Stage-rail (vertical fixed-shape pipeline UI) in docforge-rework — replaced the canvas editor as the default pipeline UX; fallback chains are the chain-accent primitive
metadata:
  type: project
---

Shipped 2026-07-02 in `src/docforge-rework/app/frontend/src/features/stage-rail/`. Replaces the
canvas pipeline studio (`features/pipeline-editor/`, now UNROUTED — kept in the tree for a future
"advanced mode" but `CollectionPipelinePage` no longer imports it; no other file references it
outside its own folder). Same route (`collection-pipeline` view) and same page-prop contract
(`initialBlob` / `onSave` / `title` / `subtitle`) as the old `PipelineEditorPage`, so swapping which
studio a host page embeds is a one-line change.

**Why the shape is fixed**: the backend's `StageViewer` (`shared/libs/pipelines/ingest/stages/`)
derives a `StageCatalog` of exactly 10 canonical stages, in a fixed run order, from ANY blob — the
skeleton never changes, only which stages are enabled/configured. The UI mirrors this 1:1: no
canvas, no add/remove-stage gestures, just per-stage toggle/provider/config/stack/chain widgets.

**Two-endpoint contract** (`PipelineDescriptor` now carries `stages_view_url` +
`stages_apply_url` alongside the canvas editor's `design_url`/`inspect_url`/`edit_url`):
- `POST stages/view {blob}` → `{stages: StageCatalog}` — pure read, no validity info.
- `POST stages/apply {blob, action}` → `{blob, stages, valid, issues, notices}` — ONE `StageAction`
  per call (`enable_stage` / `disable_stage` / `set_provider` / `set_config` / `set_chain` /
  `set_stack`), always returns a buildable blob (server handles dependency cascades — e.g.
  disabling `render` auto-disables `enrich` with a notice, never a hard error). `notices: string[]`
  is new and MUST always be shown (`NoticesBar`) — it's the only signal a cascade happened.

**Config-schema resolution is genuinely ambiguous from the API alone — solved generically, not
via stage-key hardcoding.** `StageView.config` never says WHICH family node's `config_schema`
describes it. The fix (`state/paletteLookup.ts::primaryNodeCard`): for a toggle-kind stage, pick
the family member whose `config_schema.properties` is non-empty (ties, e.g. metagen's
`chunk`/`document` kinds, share an identical schema by construction, so "first match" is safe).
For provider-kind stages the schema is unambiguous (`family` + `stage.provider`); for stack/chain
items it's unambiguous too (`family` + the item's own `kind`). Always send `set_config` with
`node: null` — the backend resolves the stage's primary node server-side
(`StageMeta.primary_node`, never exposed to the frontend).

**Local-mirror-then-debounce, but at the StageView[] grain, not the blob grain.** Typing (a config
field, a chain step's `score_below`, a stack method's config) mutates a local copy of `stages`
immediately for responsiveness, then a debounced `/apply` resend follows — same pattern as the
canvas editor's `localEdits.ts`/`applyLocalThenDebouncedEdit`, but operating on the product-level
`StageView[]` array instead of the graph `GroupBlob`, because that's what's actually rendered here.
Discrete edits (toggle, set_provider, add/remove/reorder a stack or chain step) go straight through,
no debounce — mirrors the canvas editor's split between "typing" and "everything else".

**Fallback chains are visually distinct, not just semantically.** One new theme token pair
`theme.color.chain` / `chainSoft` (cyan, `#22d3ee`) — deliberately a different hue from every
existing status color (accent blue, ok green, warn amber, error red, loop purple) so a chain block
(`ChainSection` + `ChainStepCard`) never reads as "just another stage option". `set_chain` and
`set_stack` are both FULL-list replacements (not a diff), so add/remove/reorder always resend the
whole ordered array.

See also [[docforge-rework-clean-slate]] in the orchestrator's cross-agent memory index.

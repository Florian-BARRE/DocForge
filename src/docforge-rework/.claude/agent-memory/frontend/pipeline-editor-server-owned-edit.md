---
name: pipeline-editor-server-owned-edit
description: Pipeline studio migrated from client-side blob mutation to server-owned POST /edit — architecture and the one deliberate exception (typing debounce).
metadata:
  type: project
---

As of 2026-07-05, `src/docforge-rework/app/frontend/src/features/pipeline-editor/` no longer
implements edit semantics client-side. `state/blobOps.ts` is READ-ONLY (getContainer,
findNodePath, orderedNodes, isForEach/isGroupNode, bindingKey/bindingFromKey, fragmentIds,
freshId, containerPathToIds). All structural mutation (chaining, healing, dangling-ref cleanup,
id disambiguation) lives server-side behind `POST /api/v1/pipelines/ingest/edit` — body
`{blob, operations: EditOperation[]}` → `{blob, valid, issues, explored, edit_error}`. The
`edit_url` comes from the same `/api/v1/pipelines` discovery payload as `design_url`/`inspect_url`
(`api/pipelines.ts::editPipeline`), never hardcoded.

**Why:** user-mandated structural goal — UI renders state and sends intentions, server owns
operations + healing + validation in ONE call, so a healing-rule change never needs a frontend PR.

**How to apply:**
- `state/editOps.ts` — the ONLY place a UI gesture becomes an `EditOperation` (buildAddNodeOp,
  buildRemoveNodeOp, buildSetBindingOp, buildSetConditionOp, etc.). Pure builders, no network.
- `PipelineEditorPage.tsx` — owns `blobLatestRef` (the synchronous "current blob" ref, updated
  both on render AND immediately inside edit handlers — do NOT rely on the `blob` state var
  itself for the next edit's base, React re-render timing can lag a queued promise chain) and
  `editQueueRef` (a `Promise` chain that SERIALIZES every `/edit` call — never fire two edits
  concurrently, always `.then()` onto the queue, so responses can't interleave and corrupt state).
- **The one exception**: typing into a config field, a condition param, or a loop's
  item_field/max_concurrency must feel instant. `state/localEdits.ts` holds 3 tiny optimistic
  local mutators (localSetConfig/localSetCondParam/localSetLoopProp) used ONLY for this — the
  keystroke updates `blobLatestRef`/React state synchronously, then a 400ms debounce (like the
  old /inspect debounce) sends ONE full-object `/edit` call (`set_config`/`set_condition` are
  full-replacement ops, not merges — the debounced call reads the CURRENT locally-mirrored
  value back out of the blob before sending). Everything else (add/remove/rewire/recipe-insert)
  is a direct, un-mirrored `/edit` call — no local blob prediction, since correctness (healing)
  can only come from the server.
- `add_node`/`add_loop` pass an explicit client-picked `node_id` (via `freshId`, now accepting a
  `reserved: Iterable<string>` param) purely so the UI can `setSelection` the instant the request
  fires, without waiting for the round-trip. A `reservedIdsRef` Set on the page prevents two rapid
  add-clicks from picking the SAME id before the first one's response lands.
- `edit_error` (impossible op OR unbuildable result) is surfaced via a small dismissible banner
  (`issues/EditErrorBanner.tsx`) next to the issues panel — NOT folded into the `issues` array,
  which stays exactly what the server returned. On `edit_error`, if the current selection was a
  just-added (not-yet-confirmed) node, it's cleared back to `{type:"none"}`.
- `/inspect` is kept ONLY for the one-time priming call right after the design/blob load (no
  operation to send yet) — every actual mutation goes through `/edit` instead, whose response
  already carries `issues`/`valid` (no follow-up `/inspect` needed).
- `explored` (ExploredNode tree) is returned by both `/inspect` and `/edit` but still isn't
  rendered anywhere in this app (`noUnusedLocals: true` in tsconfig — don't store it in state
  unless something will actually read it, or `tsc` will fail the build).

---
name: pattern-config-tree-renderer
description: How the generic config_tree renderer pairs chain↔gate and where edit-path correctness can break
metadata:
  type: pattern
---

The shared pipeline config editor (`app/frontend/src/components/ui/RecursiveFieldRenderer.tsx`)
is a GENERIC renderer over the discovery `config_tree` (ConfigNode[]). It must stay
stage-agnostic — no hardcoded stage names or field lists.

**Chain↔gate pairing (the high-risk part):**
- `gateSiblingSegFor(chainSeg)`: `"chain"→"gate"`, `"X_chain"→"X_gate"`, else null.
- For each `kind:"chain"` node it finds a sibling `kind:"object"` whose last path segment
  matches, tracks consumed gates in a `Set` (identity on the ConfigNode ref), then
  `otherNodes = nodes \ chains \ consumedGates`. Guarantees: every child renders once;
  consumed gate never also renders standalone; orphan chain (ladder alone) and orphan gate
  (object section) both still render. Verified for Enrich (3 pairs + chart_to_data scalar)
  and Embed (1 pair + sparse provider_union NOT swallowed).

**Why edits land on the right path:** all read/write go through `readValue(absPath)`/
`writeValue(absPath)` keyed on the node's ABSOLUTE `node.path`. `StageConfigPanel` strips
the `patch.<prefix>.` tree prefix and delegates to `readPath`/`setPath` on the local draft.
Each chain+gate pair is captured per-iteration in `pairs.map`, so each `ChainLadder` gets
its OWN `gateNode`; `findGateField(gateNode, suffix)` then resolves that group's child path.
No shared/stale closure over the first gate — confirmed no cross-wiring.

**provider_union nesting:** pickers carry their own last-segment `readParam`/`writeParam`
re-rooted at their value object; nested unions (chunk split_method → semantic → embed) work
because each picker re-roots. The `renderChildren` render-prop avoids a module cycle.

**When reviewing changes here, check:** (1) no node dropped/duplicated, (2) gate edits write
to the paired gate's own children (no index/closure bug across the multi-pair loop), (3) no
stage-name hardcoding, (4) repeated child components don't reuse static DOM ids
(see [[antipattern-static-dom-ids]]).

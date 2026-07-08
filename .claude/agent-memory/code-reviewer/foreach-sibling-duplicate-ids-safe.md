---
name: foreach-sibling-duplicate-ids-safe
description: Sibling ForEach bodies may reuse the same group/node ids — node ids are per-scope, not global; here's what to check before approving.
metadata:
  type: project
---

# Duplicate node ids across sibling subgraphs are SAFE (scoped, not global)

Two sibling `ForEach` bodies can legitimately reuse the **same** group id and node ids (e.g. both
`meta_chunk_loop` and `meta_doc_loop` bodies use group `metagen_path` with nodes `gen_0`/`skip`).
This BUILDS + VALIDATES + RUNS because node-id uniqueness is enforced **per containing group**, and
nothing in the runtime keys state by a *globally* unique id. Confirmed safe in P5c (metagen externalization).

**Why:** the engine and its edges never assume global id uniqueness. The five places a global-id
assumption *would* bite, and why each is fine:
1. `FlowEngine.__child_by_id(group, id)` iterates `group.children` — lookup is per-group.
2. `_run_group` allocates fresh `node_outputs={}` and `visited=set()` per call; each ForEach item runs
   its body as its own group run, so `gen_0` outputs never cross between the two loops.
3. The execution trace is a **tree**: foreach child records are nested under the parent's record
   (`children=child_records`) keyed by the UNIQUE parent loop id; child ids are re-labelled
   `f"{body.id}[{index}]"` only within that parent — never flattened into a global id→record dict.
4. Worker progress (`worker/backend/libs/jobs/progress.py`) tracks ONLY top-level root ids
   (`if event.node_id not in self._roots: return`); all roots are unique — loop-body ids are ignored.
5. Persistence translator keys by schema `field_name`/`spec.id`, never by node id.
6. There is currently **no** fingerprint / node-cache in the tree, so the old
   [[fingerprint_stage_flag_gap]] global-id-keying concern is moot here.

**How to apply:** when a change introduces a second (or Nth) `ForEach` with a body that mirrors an
existing one, duplicate ids across the sibling bodies are NOT a finding by themselves. Only flag if
new code introduces a place that flattens the trace tree by node id, keys progress/cache by a
non-root id, or otherwise assumes global uniqueness. Related: [[foreach-primitive-traps]],
[[foreach-chain-terminal-item-type]].

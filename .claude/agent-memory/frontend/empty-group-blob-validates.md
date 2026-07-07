---
name: empty-group-blob-validates
description: An empty pipeline group ({"node_type":"group","id":"x","nodes":[]}) is NOT a valid 422 test case — the validator skips the entry-node check when there are no children
metadata:
  type: project
---

`GraphValidator.__validate_group` only requires exactly one entry node `if group.children:` —
an empty group (`{"node_type":"group","id":"x","nodes":[],"transitions":[],"bindings":{}}`) has
zero children, so that check (and every per-child check) is skipped entirely. PATCHing a
collection's pipeline with this exact blob returns **200**, not 422 — verified live 2026-07-04.

**Why:** this shape looks intuitively "broken" (no nodes at all) but the validator only reports
issues about nodes/transitions/bindings that exist; a graph with nothing in it violates none of
those checks.

**How to apply:** to actually exercise the 422 path (e.g. for a live smoke test or a manual repro),
use a blob with a real structural defect instead — the cheapest one: a single action node with an
unbound required consumes slot, e.g.
`{"node_type":"group","id":"x","nodes":[{"node_type":"action","id":"n1","family":"intake","kind":"admission","config":{}}],"transitions":[],"bindings":{}}`.
This returns 422 with `detail` = a list of `{code, location, message}` (here three
`missing_binding` issues, one per unbound slot) — the exact shape `ApiIssueList` /
`normalizeDetail` in `api/http.ts` expect.

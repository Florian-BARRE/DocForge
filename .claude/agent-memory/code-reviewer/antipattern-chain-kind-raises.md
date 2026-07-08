---
name: antipattern-chain-kind-raises
description: StageCompiler chain/provider paths raise KeyError on an unknown kind instead of emitting a notice, breaking its "never an exception" contract
metadata:
  type: feedback
---

In `shared/libs/pipelines/ingest/stages/compiler.py`, `StageCompiler`'s own Code Summary states:
"A nonsensical action (unknown stage, a toggle on a fixed stage) is DATA — a notice is emitted and
the blob is unchanged, never an exception."

**Anti-pattern to watch for:** any action handler that reaches `ChainRules.complete_steps` /
`ChainRules.reset_config` / `ChainRules.duplicate_unique_notices` with a user-supplied `kind` that
is never validated against `NodeRegistry.kinds(family)` first. `NodeRegistry.get(family, kind)`
**raises KeyError** on an unknown kind (registry.py ~line 137), so an invalid kind crashes instead
of becoming a notice.

Known exposure (Phase 3 chain-generalization): `SetProvider(parse, <bad kind>)` routes through the
chain path (`__set_provider` → `__set_stage_chain`) and skips the `kind not in NodeRegistry.kinds`
guard that the single-provider branch (chunk/embed) has — so it raises where `SetProvider(chunk,
<bad kind>)` cleanly emits `'<kind>' is not a '<family>' provider`. Same latent gap in
`__set_enrich_chain` / `__set_stage_chain` / `__set_stack` for `SetChain`/`SetStack`.

**Why:** the studio UI only offers registry kinds, so it's low real-world reachability — but the
headless/`/apply` surface and tests can send arbitrary kinds, and the compiler's whole design
promise is data-not-exceptions.

**How to apply:** when reviewing a new stage action or chain rule, confirm the kind is validated
(or `ChainRules` guards unknown kinds and returns a notice) before any `NodeRegistry.get`. Flag as
MEDIUM: a contract violation, not a crash the happy path hits.

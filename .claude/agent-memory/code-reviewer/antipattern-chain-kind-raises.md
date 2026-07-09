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

Status (audited 2026-07-09, commit ca39197): the chain paths are now GUARDED —
`__set_enrich_chain` uses `ChainRules.unknown_kind_notices`, and `__set_stage_chain` /
`__set_provider(parse|embed)` route through `ChainRules.resolve` which returns `(None, notices)`
on an unknown kind. `SetProvider(chunk, <bad>)` is guarded by an explicit
`kind not in NodeRegistry.kinds` check. The nested llm chain in `__resolve_llm_chain` is guarded
too. **The ONE remaining hole: `StageCompiler.__set_stack` (compiler.py:314-315)** calls
`ChainRules.reset_config("contextualize", step.kind)` on each StackMethod kind with NO unknown-kind
guard → `NodeRegistry.get` raises KeyError. Reproduced: `SetStack(stage="contextualize",
steps=[StackMethod(kind="does_not_exist")])` raises `KeyError` instead of a notice; in the
`/ingest/stages/apply` route (router.py:199, `stage_compiler.apply` NOT wrapped in try) it becomes
a 500. No test covers set_stack with a bad kind. Fix: prepend a
`NodeRegistry.kinds("contextualize")` membership check per step and emit a notice, mirroring
`__set_provider`'s chunk branch.

**Why:** the studio UI only offers registry kinds, so it's low real-world reachability — but the
headless/`/apply` surface and tests can send arbitrary kinds, and the compiler's whole design
promise is data-not-exceptions.

**How to apply:** when reviewing a new stage action or chain rule, confirm the kind is validated
(or `ChainRules` guards unknown kinds and returns a notice) before any `NodeRegistry.get`. Flag as
MEDIUM: a contract violation, not a crash the happy path hits.

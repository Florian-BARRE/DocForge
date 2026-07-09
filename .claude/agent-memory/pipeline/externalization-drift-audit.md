---
name: externalization-drift-audit
description: Post-P6 adversarial audit result — where the chain-externalization stayed clean vs the one real copy-paste drift (the two ForEach body builders); the collapse fix and the Segment-vs-StackPosition non-issue
metadata:
  type: project
---

Adversarial audit (2026-07-09) confronting the post-P1–P6 stage layer against the owner's clean-foundation
mental model. **Verdict: the 3-part principle (pure engine · uniform node · ONE assembler) is INTACT.**
The chain externalization did NOT devolve into N per-stage patches. Findings, so a future agent does not
re-litigate the whole tree:

**Genuinely SHARED (do not "unify" — already single, reused 5×):**
- `ChainFragmentBuilder` (`build/chain.py`) — the ONLY chain-topology emitter: parse/embed (`segments.py`),
  enrich (`enrich_body.py`), metagen (`metagen_body.py`), contextualize (`contextualize_body.py`).
- `ChainWalker.head/walk` (`stages/chain_walk.py`) — the ONLY reverse reader, same 5 sites.
- `ChainRules.resolve` (`stages/chain_rules.py`) — the ONLY build-safe config defaulting/validation.
- `IngestAssembler.assemble` — sole wiring owner; reads each `segment.output` uniformly (FromNode stock /
  FromFirst chain). `default_blob() == assemble(default_state())` → default and edited blobs share ONE path.
- Engine (`engine/core.py`) is stage-agnostic: `__dispatch` = exactly ActionNode/ForEach/Group, no
  chain/stage branches. Transitions = the 5 conditions only; `ScoreBelow` gated to `ScoredOutput` at
  runtime (`core.py:123-128`). No `CHAIN` StageKind — chains are a SHAPE of a PROVIDER/TOGGLE stage, not a
  special stage type (`spec.py` StageKind = FIXED/TOGGLE/PROVIDER/STACK).

**The ONE real drift (D1, genuine copy-paste — collapse when touched):** `metagen_body.py` and
`contextualize_body.py` are ~95% identical (both: `ChainFragmentBuilder.build(scored=False)` → copy
nodes/transitions/bindings → if on_error wants a terminal, append node + `Transition(exits[-1]→terminal,
OnFailure)` + bind item field → `GroupNodeBlob`). Every difference is a PARAMETER (body_id/prefix,
output_field values/completion, item field request/prompt, terminal (metagen,metagen_skip)/(contextualize,
keep_raw), on_error enum). Zero structural divergence. Fix: one `ForEachChainBodyBuilder.build(*, body_id,
prefix, family, item_field, output_field, chain, terminal:(fam,kind)|None)` in `build/`, callers compute
`terminal` from their on_error. ~160 lines → ~55 + two thin call sites, byte-output identical.

**Thinner echoes (optional):** D2 — `MetagenReader.chain` and `ContextualizeReader.__chain` share an
un-extracted "find loop by over.node_id==prep.id + ChainWalker + 1-step default" kernel (`__loop` is
byte-identical); the OUTER discovery legitimately differs (metagen: 2 preps by kind; contextualize: stack
order + simple methods + skip llm_apply) → extract only the kernel. D3 — "which stages are chains" map
declared twice: `compiler._CHAIN_STAGES/_METAGEN_CHAINS` and `view.__CHAIN_STAGES/__METAGEN_CHAINS`; hang
the field name off `StageMeta` (spec.py) instead.

**Non-issue cleared:** `Segment` (one per STAGE) vs `StackPosition` (one per stack SLOT) are NOT competing
abstractions — they NEST (contextualize is one Segment built from many StackPositions; a stack needs
per-slot anchors a single `Segment.output` can't express). Only cost: `ContextualizeStack.positions()`
recomputed in both `segments.py` and `assembler.py` — cheap layer-independence recompute, leave it.

See also [[metagen-externalization]], [[selectable-flag]], [[chain-mechanism]].

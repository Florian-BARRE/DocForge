---
name: stage-rail-chain-contract
description: How the stage-rail's fallback-chain editing wire contract actually works (set_chain slot semantics, scored-vs-failure-only, the contextualize llm nested chain) — non-obvious backend invariants that are easy to get wrong from the frontend alone.
metadata:
  type: project
---

The stage rail (`src/docforge-rework/app/frontend/src/features/stage-rail/`) renders every
chain-bearing stage generically via `StageView.chains: ChainView[]`, but the WIRE contract for
editing a chain is subtler than the view payload suggests. Three facts worth re-deriving-by-reading
before touching this again, since they are easy to get wrong purely from the TS types:

**1. `set_chain`'s `slot` must be `null` for a stage-owned chain, never the view's `slot` verbatim.**
Backend: `shared/libs/pipelines/ingest/stages/compiler.py::__set_chain` — `slot=None` means "the
stage itself is the chain site" (parse, embed, metagen_chunk, metagen_document); any non-null slot
is routed to `__set_enrich_chain`, which immediately no-ops with a notice unless
`stage == "enrich"`. But `StageViewer.__stage_chain_view` (view.py) sets `ChainView.slot =
meta.key` for these stage-owned chains — i.e. the view's slot EQUALS the stage's own key. The rule
`chainActionSlot(stageKey, viewSlot) = viewSlot === stageKey ? null : viewSlot` (in
`state/stageOps.ts`) is the one place that derives the correct wire slot. Before this fix (found and
patched 2026-07-09), the frontend always sent the view's slot literally, which meant editing parse's
or embed's or metagen's chain silently no-opped (a notice fired, nothing changed) while LOOKING
editable in the UI — a real, live bug, not a hypothetical one. Confirmed against
`tests/units/stages/test_parse_chain.py` / `test_embed_chain.py`, which only ever call
`SetChain(stage=..., slot=None, ...)`.

**2. The contextualize `llm` method's chain is NOT edited through `set_chain` at all.**
`StackMethod.chain: ChainSpec | None` carries it; `StageViewer.__stack_chain_views` surfaces a
read-only `ChainView` (slot `contextualize.{index}`) purely for display parity, but
`StageCompiler.__set_enrich_chain` rejects any `stage != "enrich"` — there is no slot the compiler
accepts for contextualize. The only way to change it is a full `set_stack` with that method's
`chain` field replaced (`StageCompiler.__set_stack` → `__resolve_llm_chain`). The rail therefore
does NOT render a generic `ChainSection` for `stage.kind === "stack"`; instead
`StackMethodCard`/`StackMethodChainSection` render the `llm` method's chain nested inside its own
card, matched to the display `ChainView` by `slot === "contextualize.{index}"`, and write back via
`set_stack` (see `buildSetStackMethodChainAction` in `state/stageOps.ts`).

**3. `score_below` is only meaningful for a SCORED family; the compiler silently drops it otherwise.**
`ChainRules.family_scored` (chain_rules.py) checks whether the family's first registered kind's
`Produces` subclasses `ScoredOutput` — parser/ocr/vlm are scored, embed/llm/structgen are not. The
palette already carries this per-node as `NodeCard.scored: boolean` (added specifically for this),
so the frontend derives it honestly via `familyIsScored(palette, family)` in
`state/paletteLookup.ts` rather than hardcoding family names. A non-scored chain's `ChainStepCard`
must not offer a threshold input at all (not even a disabled one) — showing it would imply an edit
that gets silently discarded server-side.

**Reusable primitive**: `ChainStepList.tsx` is the shared ordered-step-list-plus-add-control used by
both the top-level `ChainSection` (stage-owned/enrich-branch chains) and the nested
`StackMethodChainSection` (the `llm` stack method's own chain) — keep any future chain-editing
surface going through this component rather than re-implementing the list.

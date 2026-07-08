---
name: foreach-chain-terminal-item-type
description: Why a ForEach body of a fallback chain + OnFailure→skip terminal is safe even though item_type() sees only the skip; how to review such topologies
metadata:
  type: project
---

# ForEach body = fallback chain + terminal: the item_type safety rule

When a ForEach body is built from a structgen/enrich chain where each step is a *success* terminal
(no OnSuccess edge) and a fail-soft node is wired `OnFailure` off the last step (metagen `skip`,
enrich equivalents), a subtlety trips reviewers. VERIFIED SAFE for P5b metagen — record the reasoning
so future P5c / enrich-body reviews don't re-derive it.

## The subtlety
- `ForEach.item_type()` (base/foreach.py) derives the expected artefact from `GraphTopology.exits`
  = child ids with **no outgoing transition**. A chain step that carries an `OnFailure→next` (or
  `OnFailure→skip`) edge IS a transition *source*, so it is EXCLUDED from `exits`.
- Result: for a chain+skip body, `GraphTopology.exits` = `{skip}` only; for a chain in `fail` mode,
  `exits` = `{last_step}` only. `item_type()` statically sees a **subset** of the nodes that can
  actually terminate an item at runtime (any step can succeed-terminate).

## Why it is safe (the invariant to check)
Safe **iff every node that can terminate an item produces the SAME single-slot Artifact**. For metagen:
every structgen step → `StructGenProduces(values: GeneratedValues)`; `metagen_skip` →
`MetagenSkipProduces(values: GeneratedValues)`. Same class, single slot. So the type `item_type()`
resolves from the lone static exit is correct for every runtime terminal.

The engine re-validates at runtime: `core.py:~295` takes the ACTUAL terminal node's single-slot output
(`group_output` = last-run node's output, core.py:405) and asserts `isinstance(value, expected)`. So a
non-uniform body is caught **loudly as an item failure — never silent corruption**. Worst case is a
loud runtime fail, not bad data.

## Review heuristic
- For any chain-based ForEach body: confirm EVERY step node AND every terminal (skip/recovery) has a
  `Produces` with exactly one slot of the SAME Artifact class. If a step could terminate with a
  different artefact, `item_type()` may still return non-None (validator PASSES) but runtime fails —
  a latent sharp edge in `item_type()` (checks static exits only, not all runtime terminals).
- `on_error` is a GRAPH EDGE, not a node flag: `skip_fields` = a model-free terminal wired
  `OnFailure` off the chain's last exit (doc survives, failed request's fields drop); `fail` = no such
  terminal, so a last-step failure propagates as a ForEach item failure = whole-run failure. Verify
  BOTH at runtime (run the engine, assert output/status), not just structurally.
- The builder must hang the skip off `fragment.exits[-1]` (the LAST/most-robust step), and must NOT
  reuse `fragment.output` (the FromFirst convergence binding) — a ForEach collects terminals directly.

Related: [[foreach-primitive-traps]], [[metagen-embed-node-traps]], [[antipattern-chain-kind-raises]].

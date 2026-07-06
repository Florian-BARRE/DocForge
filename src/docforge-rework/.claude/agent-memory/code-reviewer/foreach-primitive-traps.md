---
name: foreach-primitive-traps
description: Review traps in the docforge-rework/shared pipelines ForEach/WhenEquals/SlotTypes primitives — non-Artifact item_type crash, ValidationError escaping per-node try/except, no ge=1 guard, progress attribution, trace duplication
metadata:
  type: project
---

Review heuristics for the NEW graph engine at `shared/libs/pipelines/` (docforge-rework rewrite — distinct from the older `common_libs`/`worker` engine covered by [[pipeline-engine-edge-selection]]). Verified empirically 2026-07-03 against the just-landed ForEach + WhenEquals + SlotTypes primitives.

**Why:** these are the traps a foreach/switch author will hit that the validator does NOT catch, so they must be checked by eye in review.

**How to apply:** when reviewing any ForEach body or the engine loop, check each:

1. **Non-Artifact terminal crashes the loop uncaught.** `base/foreach.py` `item_type()` accepts ANY plain class as the terminal slot (a `Produces{kind: str}` yields `T=str`) because `SlotTypes.element` only checks `isinstance(annotation, type)`. The validator then reports 0 issues, but at run time `ForEachItems.items: list[Artifact]` rejects the scalar → `pydantic.ValidationError` escapes `__run_foreach` (unwrapped) and the WHOLE run crashes instead of a FAILED record. Fix: `item_type()` must also require `issubclass(element, Artifact)` (Artifact is already imported there) → falls back to `foreach_invalid_body` + a graceful FAILED record.

2. **Engine per-node try/except catches only `ResolutionError`, not `ValidationError`.** `engine/core.py __run_action` wraps `InputResolver.resolve` in `except ResolutionError`, but `resolve` ends with `consumes_model(**values)` which raises pydantic `ValidationError` on a type mismatch. In a foreach this means a single off-type item crashes the entire loop rather than failing that one item (contradicts the "ANY item failure → FAILED record" contract). Same root-cause family as #1.

3. **No `ge=1` guard on direct `ForEach(...)` construction.** Only `build/blob.py ForEachNodeBlob.max_concurrency` has `Field(ge=1)`. Programmatic assembly (not via a blob) with `max_concurrency=0` → `asyncio.Semaphore(0)` locked forever → the run HANGS with no timeout; negative → uncaught `ValueError`. Guard in `ForEach.__init__`.

3. **Progress events can't be attributed to items.** `__run_child` emits START/END with the original child `node.id` ('clf', 'emit'…) and no item index; concurrent items interleave identical ids. The per-item record is renamed `body[i]` only AFTER `gather`, so the live feed (SSE/UI) cannot tell items apart.

4. **`foreach record.output = ForEachItems.model_dump()` duplicates every item value** into the trace — with bytes-carrying artefacts (figure crops) this doubles a document's images in memory (same latent issue as `resolved_input`).

Confirmed-GOOD (no fix needed): switch + default (WhenEquals rank 3 beats OnSuccess rank 2, unmatched falls through) works; foreach-as-body-terminal degrades to `foreach_invalid_body`; node instances are shared across concurrent item runs but the current inventory is stateless in `run()` (latent race only if a future node mutates `self` in `run()`); blob smart-union (Action/Group/ForEach) is unambiguous under `extra="forbid"`.

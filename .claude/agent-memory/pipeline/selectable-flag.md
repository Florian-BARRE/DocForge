---
name: selectable-flag
description: The `selectable` describe-contract flag that hides internal wiring node kinds from the discovery palette, and the contextualize LLM externalization (P6) that motivated it
metadata:
  type: project
---

**`selectable` is a describe-contract flag (P6a) that hides INTERNAL wiring kinds from the palette
without unregistering them.** It lives as `AbstractNode.SELECTABLE: bool = True` (class attr, next to
`UNIQUE_IN_GRAPH`), surfaces on `NodeDescription.selectable`, is set in `ActionNode.describe()`
(`selectable=cls.SELECTABLE`). The ONLY filter chokepoint is `NodeRegistry.catalog(family)` — it drops
cards whose `.selectable is False`. `catalog` has exactly ONE caller (`FamilyCatalog.from_family`), so
filtering there hides internal kinds from BOTH the lean and full palette while `kinds()` / `get()` /
`describe()` still reach them (the graph engine + headless edit deserialise by `(family, kind)`, never
via the palette). No blob/graph change — discovery output only.

**Kinds marked `SELECTABLE=False`:** metagen `chunk_prep · document_prep · chunk_apply · document_apply
· metagen_skip`; contextualize `llm_apply · keep_raw` (post-P6b: `llm_prep` was renamed to `llm` and
made `SELECTABLE=True` — it IS the user-pickable method now). These are stage-builder wiring
(prep/apply nodes + fail-soft ForEach terminals), never a user-picked stage METHOD. Test:
`test_design_surface.py::test_palette_hides_internal_kinds_but_keeps_them_registered` (palette disjoint
from the internal set, each internal kind still `NodeRegistry.get(...).describe()`-able).

**Contextualize LLM externalization (P6b, DONE):** mirrors P5 metagen, adapted to a STACK position.
The inline `(contextualize, llm)` monolith was DELETED; the prep IS now the canonical
`(contextualize, llm)` (kind renamed `llm_prep→llm`, `SELECTABLE=True`, lives in `nodes/contextualize/llm/`,
`llm_prep/` dir removed). The stage layer emits, per llm stack position,
`prep → ForEach(over=prep.prompts, item=prompt, body=generic-llm chain [+ keep_raw]) → llm_apply`.
- `StackMethod.chain: ChainSpec | None` (models.py) — None for simple methods (doc_meta/breadcrumb/
  sliding), the generic-`llm` chain for the llm method, edited via **SetStack** (NOT a position-addressed
  SetChain). `ChainSpec` MOVED from state.py → models.py (state re-exports it) so StackMethod can carry it
  without a models↔state import cycle.
- `stages/contextualize_stack.py` (`StackPosition` dataclass + `ContextualizeStack.positions(state)`) is
  the richer successor of the deleted `contextualize_ids`, consumed by BOTH `SegmentBuilder.__contextualize`
  (node emission) and `IngestAssembler.__bind_stack` (spine threading). Ids: `ctx_llm{,_loop,_apply}`,
  `ctx_llm_2{...}` — llm position repeatable (two situating passes legit). `apply.chunks` binds the SAME
  incoming chunks as the prep (like metagen's meta_chunk_apply), `apply.completions=FromNode(loop,"items")`.
- `stages/contextualize_body.py` (`ContextualizeBodyBuilder`) = MetagenBodyBuilder sibling: llm NON-scored
  (OnFailure-only, no ScoreBelow), `step_inputs={"prompt": FromGroupInput("prompt")}`, `keep_raw` terminal
  wired OnFailure off the last step when on_error==keep_raw. Body id `ctx_path`, keep id `keep`.
- `stages/contextualize_read.py` (`ContextualizeReader`) walks the stack: an `llm` prep starts a position,
  finds its loop (`over.node_id==prep.id`), walks the generic-`llm` chain via `ChainWalker` (family `{"llm"}`;
  keep_raw is family contextualize → naturally excluded), SKIPS the paired `llm_apply`. `reader.__stack`
  delegates to it. `on_error` round-trips through the PREP config (not re-derived from body).
- Compiler `__set_stack` resolves each llm method's chain via `ChainRules` (complete_steps +
  drop_unscored_thresholds + duplicate_unique + unknown-kind). View surfaces one ChainView per llm method.
  Round-trip idempotent for 1-step AND 2-step llm stacks (`test_stack.py`).
- **BYTE-SAFE:** default stack is doc_meta+breadcrumb (no llm) → `default_blob.json` UNCHANGED (simple-method
  path still emits exactly `ctx_meta`/`ctx_breadcrumb`). REAL-VIEW parity proven with a fake llm that ECHOES
  the document view (section + full scope) — the prep's view flows through prep→chain→apply.

**(historical) Contextualize LLM externalization (P6a):** the intermediate step — the monolith STILL
existed and the prep used a TEMPORARY kind `llm_prep` (byte-safe: NodeRegistry rejects a duplicate kind, so
the replacement couldn't register as `llm` while the monolith held it). P6b did the atomic delete+rename.
The prep → ForEach shape was:
The chain unit is the GENERIC `llm` family (`LlmChatConsumes{prompt} → LlmChatProduces{completion}`),
NOT a dedicated contextualize kind — contextualize is strictly 1 chunk → 1 prompt → 1 completion, so the
apply node joins by POSITION (`zip(chunks, completions, strict=True)`), no chunk_id keying (unlike
metagen's GenerationRequest.chunk_id). `on_error` is a GRAPH EDGE: `keep_raw` wires a `keep_raw`
terminal OnFailure off the chain's last step (empty `Completion` → apply's `_with_context` no-ops →
chunk raw, doc survives); `fail` omits it (last-step failure = ForEach item failure = run fails).

**P6a sequencing (byte-safe, non-obvious):** the monolith `(contextualize, llm)` STAYS registered +
wired in P6a (stage layer untouched, golden `default_blob.json` byte-identical). So the prep CANNOT
also register as `(contextualize, llm)` — the NodeRegistry rejects a duplicate kind in a family. The
prep therefore uses a TEMPORARY kind **`llm_prep`** in P6a; P6b does the atomic monolith-delete +
rename `llm_prep → llm` + stage rewire. This "add nodes under non-colliding kinds while the monolith
stays" is the ONLY byte-safe option — registering the replacement under the real kind now would collide.

**Shared view helpers (extracted P6a):** the document-view logic (`truncate / full_view / scoped_view`
+ `situate_messages`) moved from the monolith into `nodes/contextualize/base/helpers.py`
(`ContextualizeViewHelpers`, static), and the `DocumentScope`/`OnChunkError` enums +
`DEFAULT_SITUATE_PROMPT` into `base/enums.py` / `base/config.py`. The monolith AND the prep both call
the helper (single source → the P6b swap stays behavior-identical). FULL view is chunk-independent →
built ONCE per run and threaded in (no O(n²) regression). The monolith's `llm/config.py` re-exports the
enums + prompt from `base` so external imports stay stable.

**Parity proof:** `tests/units/nodes/test_contextualize_topology.py` runs the STILL-PRESENT monolith and
the new topology on the same fake situating fn and asserts identical grown `chunk.context` (1-step chain,
order-correct, keep_raw, fail). Fake llm recovers chunk text from the prompt's `<chunk>…</chunk>` block.

See also [[metagen-externalization]] (the P5 precedent this mirrors) and [[chain-mechanism]].

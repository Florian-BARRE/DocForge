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
· metagen_skip`; contextualize `llm_prep · llm_apply · keep_raw`. These are stage-builder wiring
(prep/apply nodes + fail-soft ForEach terminals), never a user-picked stage METHOD. Test:
`test_design_surface.py::test_palette_hides_internal_kinds_but_keeps_them_registered` (palette disjoint
from the internal set, each internal kind still `NodeRegistry.get(...).describe()`-able).

**Contextualize LLM externalization (P6a, done — P6b pending):** mirrors P5 metagen. The inline
`(contextualize, llm)` monolith (`nodes/contextualize/llm/`) is being externalised into
`prep → ForEach(over=prep.prompts, item=prompt, body=generic-llm chain [+ keep_raw]) → llm_apply`.
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

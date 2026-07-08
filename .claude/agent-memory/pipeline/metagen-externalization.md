---
name: metagen-externalization
description: P5 (complete) externalization of the metagen LLM call into a prep→ForEach(structgen chain)→apply topology — the emitted node ids, the on_error/max_concurrency stage-config home on the prep, the multi-loop reader disambiguation, and the ForEach exits/item_type fact behind the fail-soft skip terminal
metadata:
  type: project
---

Metagen's inline LLM call was externalized (P5a/b/c, **complete**) into a **generic `structgen`
capability** + **thin metagen prep/apply nodes** wired by a ForEach, mirroring how enrich externalized
figure enrichment. P5c rewired the stage layer to emit this topology and **DELETED** the old
monolithic `(metagen, document)`/`(metagen, chunk)` nodes (`metagen/{chunk,document}/` gone) — they no
longer exist. The stage layer is now the sole emitter of the new topology.

**The topology (per scope):** `prep → ForEach(over=prep.requests, item=request, body) → apply`.
- `structgen` capability (`shared/libs/pipelines/nodes/structgen/`): consumes a `GenerationRequest`
  (public_models), produces `GeneratedValues`, does the structured-output call + strict coercion
  (`StructGenHelpers.object_schema`/`coerce`). **NON-scored** → chains escalate on `OnFailure` only.
  Endpoint is dual-sourced per field: a step config override wins, else the request's own endpoint.
- metagen nodes (all family `metagen`, `ingest/nodes/metagen/{prep,apply,skip}/`):
  `chunk_prep`/`document_prep` (resolve targets loudly + group per grouping knob → emit one
  `GenerationRequest` per call group), `chunk_apply`/`document_apply` (merge `GeneratedValues` back —
  chunk: index by chunk_id, merge-not-clobber into `generated_meta`; doc: merge all dicts into one
  `GeneratedDocumentMeta`), `metagen_skip` (model-free fail-soft terminal).
- Prep reuses `BaseMetagenNode._resolve_targets`/`_document_text` by **subclassing** it
  (`BaseMetagenPrep(BaseMetagenNode)`). P5c **deleted the now-dead `_generate`/`_generate_values`**
  from `BaseMetagenNode` (only the removed monoliths used them — coercion lives in `StructGenHelpers`);
  the base is now model-free (just target resolution + document view).
- **Stage-config home (non-obvious, P5c decision):** `MetagenPrepConfig` **carries `on_error` +
  `max_concurrency`** as fields even though prep.run() ignores them. They are STAGE-EXECUTION knobs the
  segment builder (`SegmentBuilder.__metagen`) reads off `state.metachunk_config`/`metadoc_config` to
  shape the ForEach `max_concurrency` and the body's skip terminal. Parking them on the stage's anchor
  node (the prep) is what lets them round-trip through the SAME `config_of(prep)` the reader/view already
  read — no new state field, no popping. `extra="forbid"` forces them to be declared fields, so a
  separate PipelineState field was NOT used. (The P5b config summary said these "left the config" — P5c
  brought them back deliberately as stage knobs; don't re-remove them without a new carrier.)

**`on_error` is a GRAPH EDGE, not a node flag** (the `MetagenBodyBuilder` mechanic,
`ingest/stages/metagen_body.py`): `skip_fields` → append a `metagen_skip` terminal wired **OnFailure
off the chain's LAST step** (`fragment.exits[-1]`); the doc survives, only that request's fields drop.
`fail` → NO skip terminal → the last step's failure has no recovery edge → the ForEach item fails →
the document fails (the ForEach "item failure = loud failure" contract).

**NON-OBVIOUS ENGINE FACT (load-bearing for any fail-soft ForEach terminal):** a chain step that
carries an `OnFailure→skip` edge is a transition SOURCE, so `GraphTopology.exits` (= nodes that are
never a source) does NOT count it as a static exit. `ForEach.item_type()` and the validator therefore
"see" ONLY the skip terminal (or, in `fail` mode, only the last step). **This still works** because
EVERY body terminal — every structgen step on success AND the skip node — produces the SAME
single-slot `GeneratedValues`, so `item_type()` resolves to `GeneratedValues` regardless of which
subset it statically sees, and the engine's runtime check `isinstance(value, expected)` in
`__run_foreach` passes for whatever node actually terminated the item (a step's success output or
skip's empty output). The collection contract holds at RUNTIME even when the static exit set misses
the success terminals. Same reasoning already held implicitly for a multi-step VLM enrich chain.

**FlowEngine does NOT raise on a failed run:** `execute()` returns `(None, record)` with
`record.status == FAILED`. A `fail`-mode parity test asserts `output is None` and the failed status —
not `pytest.raises`.

**Node ids the stage layer emits (per scope):** `meta_chunk_{prep,loop,apply}` +
`meta_doc_{prep,loop,apply}` (the loop is a top-level `ForEachNodeBlob`). The chunks spine anchor
`chunks_final` = `FromNode(meta_chunk_apply, chunks)`; bundle `document_meta` =
`FromNode(meta_doc_apply, meta)`. Any test/edit-op that hardcoded the old `meta_chunk`/`meta_doc` ids
must use these. Cross-segment edge is `meta_chunk_apply → meta_doc_prep`.

**Multi-loop reader disambiguation (P5c, subtle):** there are now THREE top-level ForEach loops
(enrich + 2 metagen). `StateReader.__enrich_loop` finds the one whose body has a `figure_classify`;
each metagen ladder is read by `MetagenReader` (new `stages/metagen_read.py`) by finding the prep
(family metagen, kind `chunk_prep`/`document_prep`) then the ForEach whose `over` FromNode points at
that prep, then walking the body's `structgen` chain. The generic chain-walk was extracted to
`stages/chain_walk.py` (`ChainWalker.head`/`walk`) and is now shared by parse/embed/enrich AND metagen
(kept `reader.py`/`metagen_read.py` under ~200 lines). Round-trip idempotent for default AND a 2-step
metagen chain (`test_stage_combinatorics.py::test_two_step_metagen_chain_round_trips_and_is_idempotent`).

**Compiler:** metagen chains are edited via a slot-less `SetChain` through `_METAGEN_CHAINS`
(`{metagen_chunk:(metachunk_chain,structgen), ...}`), handled in `__set_stage_chain` alongside
`_CHAIN_STAGES` (shared `__rebuild_stage_chain`). Metagen is NOT in `_CHAIN_STAGES` so `set_config`
keeps hitting the PREP config via `_CONFIGS`. `structgen` non-scored → `drop_unscored_thresholds`
strips any score_below with a notice. View exposes a `structgen` `ChainView` PLUS the prep config
(TOGGLE that also carries a chain, like enrich). `structgen` added to `IngestPipeline.FAMILIES`.

**Parity proof (P5c):** the monolith is gone, so `test_metagen_topology.py` no longer compares to it —
it asserts the ABSOLUTE frozen values (locked in P5b) for both scopes × {combined, per_field} +
merge-not-clobber + doc join + skip/fail + loud bad-target. Fake-structgen gotcha: the document VIEW
contains every chunk's raw text, so a sentinel-based failure must gate on `request.chunk_id is not None`
(chunk scope) to keep the doc request succeeding. Worker e2e (`test_variant_pipeline`) passed UNCHANGED
— the DeliveryBundle output contract (bundle.document_meta / chunk.generated_meta) is untouched.

See also [[chain-mechanism]] (the `ChainFragmentBuilder` this body builder reuses) and [[stage-layer]].

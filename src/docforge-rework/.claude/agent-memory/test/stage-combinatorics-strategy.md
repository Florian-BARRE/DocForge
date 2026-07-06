---
name: stage-combinatorics-strategy
description: How to hit all 2^5=32 toggle combinations of the optional ingestion stages directly, bypassing StageCompiler's dependency cascade which would otherwise collapse some vectors.
metadata:
  type: project
---

The 5 optional ingestion stages (`render`, `enrich`, `metagen_chunk`, `metagen_document`,
`embed`) are booleans on `shared_libs.pipelines.ingest.stages.PipelineState`
(`render_on`, `enrich_on`, `metachunk_on`, `metadoc_on`, `embed_on`). `enrich` `requires`
`render` in `StageSpecs.ORDER` — `StageCompiler.__cascade_enable`/`__cascade_disable` enforce
this when driving toggles through `EnableStage`/`DisableStage` actions, which means going
through the compiler from `default_state()` can only ever reach ~24 of the 32 combos (enrich=on
+ render=off is unreachable via cascade).

**The test in `tests/units/stages/test_stage_combinatorics.py` bypasses the compiler entirely**:
it builds each of the 32 raw boolean vectors directly via
`default_state().model_copy(update={...5 toggles...})` and calls
`IngestAssembler.assemble(state)` straight away. This is deliberate and stronger than exercising
only the cascade-reachable subset — it proves the ASSEMBLER's wiring rules (the IR/chunks spine
rebinding logic in `assembler.py::__bindings`) are correct for literally any combination, not
just the ones the compiler would ever produce. The compiler's cascade correctness itself
(enabling enrich pulls render back on, disabling render cascades enrich off) is a SEPARATE,
narrower concern that still needs its own test (not yet written as of 2026-07-05 — see the
open backlog in the test agent's last report).

Starting every combo from `default_state()` (not a bare `PipelineState()`) matters: the bare
default leaves `classify_config`/`chains`/etc. empty, which would fail to build (required
fields like `base_url` missing) regardless of the toggle combination — `default_state()`
already has build-safe non-empty configs for every stage, so only the 5 toggles under test vary.

128 = 32 combos × 4 checks (build+validate clean, reader round-trips the 5 toggles, view is
idempotent on reassembly, IR/bundle rebindings match the expected producer for that combo).

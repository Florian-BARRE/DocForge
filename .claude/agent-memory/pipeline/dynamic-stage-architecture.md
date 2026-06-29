---
name: dynamic-stage-architecture
description: The self-describing Pipeline→Stage→Step→Brick refactor — frozen plan, PR-1 contracts/adapters (unwired), how the strangler migration proceeds
metadata:
  type: project
---

# Dynamic self-describing stage architecture (strangler refactor)

The hand-wired 7-stage pipeline is being re-founded on **3 abstract contracts** —
`AbstractPipeline → AbstractStage → AbstractStep (└ ChainStep)` over a `Brick` layer (Chain →
providers). Fat-abstract / thin-concrete: all execution logic (topo order, tracking, error
policy, caching, `describe()`) lives in the abstracts; a concrete stage only DECLARES.

**Why:** collapse the ~9 edit-sites-per-stage cost; make `/discovery` 100% backend-generated
(zero hardcoded UI text); enable a chunk-filter stage + doc/chunk activation to ride the same
contract. Frozen plan: `docs/rpi/dynamic-stage-architecture/plan.md`; current-state map:
`docs/rpi/dynamic-stage-architecture/research.md`. Approved by the user 2026-06-29.

**How to apply:** delivery is a strangler migration, PR by PR, each green:
- **PR-1 (DONE):** contracts + context + tracking + 7 adapters, **purely additive + UNWIRED** —
  nothing in the worker/production path imports them yet, so behavior is byte-for-byte unchanged
  (812 units green = 780 existing + 32 new). DO NOT assume the worker uses these yet.
- **PR-2 (DONE):** `assembly/stage_registry.py` (`@register_stage`/`auto_import_stages`/`topo_order`/
  `validate_wiring`, copy of `_registry.py`) + `assembly/stage_assembler.py` (`build_pipeline`) +
  additive PipelineConfig shim. Still UNWIRED (worker keeps legacy StageEngine). 837 units green
  (817 + 20). Key facts below.
- **PR-3 (DONE):** dynamic engine wired behind `PIPELINE_DYNAMIC_STAGES` (default false); the engine
  loop lives in `AbstractPipeline.run` driven by injected `EngineHooks`; worker `DynamicStageEngine`
  + `WorkerEngineHooks` provide the I/O (node-cache via `CacheDispatch`, persist, collection gate).
- **PR-4 (DONE):** flipped the flag live on GPU — full pipeline live suite passed (258).
- **PR-5 (DONE):** dynamic engine is now the **SOLE** path. The flag is GONE. The legacy orchestrator
  is DELETED — see "PR-5 deletions" below. Suite: 844 units green.
- **P1b inc-1 (DONE):** physical reorg skeleton + PARSE migrated native. See "P1b reorg" below.
- **P1b inc-2 (DONE):** ingest/chunk/contextualize/metagen migrated native (855 units green).
- **P1b inc-3 (DONE):** enrich (S2) + embed_index (S6) migrated native; the `adapters/` package +
  `LegacyStageAdapter` + `DelegatingStep` are **DELETED** (all 7 stages native). 862 units green +
  live-parity green (17). `_STAGE_PACKAGES` now walks ONLY `ingest.stages`. Test scaffolding that used
  `DelegatingStep` now uses `tests/units/dynamic_step_helpers.py::RunnerStep`. Decomposition outcomes:
  - **enrich = ONE executing step** (`EnrichStep` → `S2EnrichStage.run`). S2 routing is per-figure +
    ATOMIC (classify→route→OCR/VLM/chart per block, interleaved provider-cache + counters); splitting
    into 4 whole-IR passes would change semantics (logic rewrite, not structural). `EnrichStage.
    describe()` is OVERRIDDEN to model the 4 conceptual sub-steps (classify always; ocr/vlm iff their
    chain exists; chart iff chart_to_data) as descriptive StepSchemas. NODE_TYPE="s2", fingerprint→
    `inner.params_for_fingerprint()`.
  - **embed_index = TWO REAL steps** (`EmbedStep` → `IndexStep`). S6 split cleanly via an
    extract-method on the INNER stage: `S6EmbedIndexStage` now exposes `embed()` (chain → typed
    `S6EmbedArtifacts`) + `index()` (ensure/upsert/persist); `run()` kept as their byte-identical
    composition. Hand-off travels via `ctx.aux["embed_artifacts"]` (key = `EMBED_ARTIFACTS_KEY`).
    IndexStep opens the PG session locally; the collection_id gate stays in the worker hooks
    (`should_run`), NOT in the stage. EmbedStep is an `IngestStep` (not ChainStep — the embedder does
    multi-batch + per-field calls, not one chain.call) but its `describe()` emits a chain-kind schema
    (category="embed" + provider ids) so the API shows the ladder. IndexStep describe = plain step.
  - Parity tests: `test_native_enrich_embed_index.py`. The empty-chunks guard moved into `embed()`
    (returns None) + `index()` (None → `S6Result(0,0,0,name)`, no Qdrant/PG I/O) — byte-identical.
- **Next:** `search/` gets the same SearchPipeline/Stage/Step treatment (inc-5), and `providers/`
  move to `pipeline/bricks/providers/` (inc-4, layer-DAG prerequisite — see "providers→bricks audit").

## providers→bricks move — layer audit (inc-4 prerequisite, NOT yet done)

Target: `common_libs.providers.*` → under `pipeline/`. The frozen rule: providers consumed ONLY at
step level. The layer DAG today: `config(1) ← providers(1) ← … ← pipeline(3)`. Moving providers under
pipeline (L3) inverts any L1/L2 importer. Findings:
- **BLOCKER = the provider CONFIG classes + registry (L1 config).** Each provider package bundles BOTH
  an `@register`-decorated `*/config.py` (an L1 concern: validation unions + `/discovery`) AND the
  runtime impl (the executable brick). `config/pipeline/_registry.py` (register/auto_import/build_union)
  + every `config/pipeline/stages/*_config.py` + `pipeline.py` import provider **config** classes.
  **Resolution:** SPLIT config-from-runtime — provider config classes + the registry stay in the config
  layer (L1); move only the runtime impls under `pipeline/bricks/providers/` (L3, imported by steps).
- **`chain` / `chain_gate` / `interfaces` are BRICKS, not providers.** `base/step/core.py`,
  `bricks/tracking/models.py`, and most `from common_libs.providers.chain import …` are about the Chain
  brick. **RELOCATED — inc-4a DONE (862 green):** `providers/chain/` (package) + `providers/chain_gate.py`
  → `pipeline/bricks/chain/` (chain_gate.py → `gate.py`); `bricks/chain/__init__` now also exports
  `ChainGate`/`ChainGateConfig`. 25 importers rewritten (`providers.chain`→`pipeline.bricks.chain`,
  `providers.chain_gate`→`…chain.gate`); the `Chain` re-export removed from `providers/__init__`.
  `base/step` + `tracking` import the brick; zero `providers.chain*` imports remain. CAVEAT: the chain
  brick still imports `providers.scoring.ScoredResult` (gate.py + run_helpers deferred) — a DOWNWARD L1
  import (allowed), but `scoring.py` is really part of the chain/gate brick; move it WITH chain in inc-4b.
  `interfaces/` was deliberately NOT moved (it's the provider Protocol layer depending on
  `providers.results`, not chain machinery — belongs in inc-4b under `bricks/providers/base`).
- **config_describer** (`pipeline/assembly/config_describer.py`) string-walks `common_libs.providers.*`
  + calls `get_configs(category)`. It's L3 (pipeline) so not a violation. **inc-4b finding:** since the
  `@register` CONFIG classes STAY in `providers/<family>/<id>/config.py`, `_PROVIDER_PACKAGES` is
  UNCHANGED — only runtimes move, so discovery auto_import strings need no edit.

## inc-4b — provider config/runtime split (DONE for ALL families, 862 green; registration verified)

ALL provider runtimes moved to `common_libs/pipeline/bricks/providers/<family>/` (subpaths preserved
so intra-family relative imports stay valid); contracts (`base.py` Protocols, `interfaces/`,
`results/`, `scoring.py`, `model_cache.py`, `lang/`, `device/{enums,snapshot}.py`) STAY at L1;
`@register` CONFIG classes STAY at L1 with `build()` lazy-importing the runtime brick (TYPE_CHECKING
+ function-local). `device_manager.py` shim DELETED (was L1, can't re-export the L3 runtime); 3 app
sites repointed to `bricks.providers.device`. `providers/__init__` is now CONTRACTS-ONLY. Each
`bricks/providers/<family>/__init__` re-exports its runtimes. Verified: get_configs counts unchanged
(embed2/ocr2/vlm1/classifier2/parser1/converter1/rerank2/llm1 — no silent auto_import loss),
`GotenbergConfig().build()` resolves to the brick, ZERO module-level (col-0) brick import under
`providers/`. config_describer `_PROVIDER_PACKAGES` UNCHANGED. Gotcha: `git mv` fails on UNTRACKED
files (json_helpers) — fall back to filesystem move + `git add`.

### (historical) inc-4b EXEMPLAR (embed/bge_server) — the pattern, since applied to all

Boundary applied (refined from the original plan):
- **CONFIG classes stay at L1** in `providers/<family>/<id>/config.py` (`@register` + merge_defaults/
  availability/build) — registry + discriminated union + /discovery untouched.
- **RUNTIME impls → `pipeline/bricks/providers/<family>/` (L3)**, consumed only by steps + chain assembler.
- **CONTRACTS stay at L1** (`providers/embed/base.py` EmbedProvider Protocol, `providers/interfaces`,
  `providers/results`, `scoring.py`). DECISION: do NOT move contracts — Protocols/dataclasses, not
  runtimes; the runtime imports them DOWNWARD (L3→L1, acyclic), config references them for typing with
  no churn. (Diverges from the coordinator's "move interfaces/results/scoring"; flagged as the cleaner
  boundary the exemplar validated.)
- **build() layering fix:** `config.build()` FUNCTION-LOCAL lazy-imports the runtime brick; module top
  has only a `TYPE_CHECKING` import (annotations are strings via `from __future__ import annotations`).
  Zero module-level L1→L3 edge → acyclic. Mirrors the metagen `_validate_and_default_chain` lazy import.
- **Exemplar moves:** `providers/embed/tei/provider.py` → `pipeline/bricks/providers/embed/tei_provider.py`
  (bge_server's runtime is the shared `TeiEmbedProvider`). Both configs building it (`bge_server/config.py`
  registered + `tei/config.py` unregistered-compat) got the lazy `build()`. Removed the runtime export from
  `providers/embed/__init__`, `providers/embed/tei/__init__`, `providers/__init__`. Repointed the 2 app
  importers (`metadata_indexer/{indexer,helpers}`) to the brick.
- **NOT yet moved (extend after go-ahead):** other embed runtimes (`composite.py`, `openai_compat/
  provider.py` — still L1, fine) + the other families (parser/ocr/vlm/classifier/rerank/llm/converter) —
  each `config.py`+`__init__` still does `from .provider import X` (same entanglement; apply the proven
  lazy pattern per family). `GotenbergConverter` + `DeviceManager` are imported by app/stage_assembler;
  handle their runtime move + lazy build similarly.
- **app/backend/libs/search/** imports embed/llm/rerank providers (hybrid/service, pipeline/engine,
  q_transform, rerank). NOT a hard violation (app is top layer), but the plan wants query-embedding to
  become a SearchPipeline STEP (inc-5). `common_libs/search/**` imports NO provider (verified).
- **storage/** + **src/mcp/** import NO provider (verified clean).

## P1b — physical reorg (one stage at a time, behind the stable contract)

Target tree (frozen): `pipeline/base/{pipeline,stage,step}/` = universal contracts (unchanged);
`pipeline/ingest/core.py` = `IngestPipeline(AbstractPipeline)` (MOVED here from worker
`dynamic/engine.py`; worker now imports it — KEY still `"ingest_pipeline"`);
`pipeline/ingest/stages/base/{stage,step}/` = `IngestStage(AbstractStage, abstract=True)` +
`IngestStep(AbstractStep)` / `IngestChainStep = ChainStep` (THIN markers, no logic);
`pipeline/ingest/stages/<name>/{core.py, steps/<step>.py}` = native stages (assembly only).

Native-stage pattern (the exemplar all migrations follow):
- `core.py`: `<Name>Stage(IngestStage)` — declares the SAME forced ClassVars the adapter did
  (KEY/NAME/DESCRIPTION/AFTER/CONFIG/CONSUMES/PRODUCES/CACHE_POLICY/ON_ERROR + NODE_TYPE/NODE_VERSION
  for node-cached). `__init__(self, inner)` keeps `self._inner = inner` (assembler does
  `stage_cls(inner)`; parity tests read `_inner`) + builds `self._steps=[<Step>(inner)]`. Node-cached
  stages OVERRIDE `fingerprint_params()` to surface the legacy params (parse → `{"parse_chain":
  sig}`; ingest → `{"converter_name","converter_version"}` from `inner._converter`).
- `steps/<step>.py`: `<Step>(IngestStep)` — single delegating step; `KEY/NAME/DESCRIPTION/CONSUMES/
  PRODUCES` = the stage's (so describe() + the fingerprint step-aggregate stay byte-identical to the
  old DelegatingStep). `run(ctx)` reads CONSUMES → `await inner.run(...)` → writes PRODUCES.
  PARSE step reads `ctx.fingerprints["parse"]` (its OWN node fp, keys the markdown blob). METAGEN
  step ALSO assembles `doc_meta` (implicit<generated<user) — the PR-1 IO-graph-closing fix.
- Name clash gotcha: stage KEY `"ingest"` → class `IngestDocStage` (NOT `IngestStage`, the base);
  its step is `IngestDocStep` (NOT `IngestStep`, the base).
- Registration: `@register_stage` on the stage; `ingest/stages/__init__` imports every native stage
  (registration backstop); `stage_registry._STAGE_PACKAGES` walks BOTH `ingest.stages` AND
  `adapters` (auto_import); `stage_assembler` backstops by importing both packages. DELETE the
  replaced adapter file + its `adapters/__init__` export so `get_stages()["<key>"]` resolves to the
  native class (KEY is unique; last registration wins).
- Parity unchanged: `build_pipeline` still yields the canonical 7-key topo order; `_build_inner`
  still builds the SAME inner legacy stage per key and the native stage wraps it — inner chain
  signatures + fingerprint_params identical. IDEMPOTENT_WRITE stages need NO fingerprint override
  (their node fp is computed but never consulted: no cache_load/store, not in EngineResult).
- Tests: `test_native_parsing_stage.py` (parse) + `test_native_ingest_stages.py` (the 4) assert
  ClassVar/round-trip/fingerprint parity + build_pipeline order; `test_dynamic_adapters.py` now
  covers ONLY the 2 remaining adapters.

## PR-5 — legacy orchestrator removed (the ingestion engine is now ONLY the dynamic path)

DELETED (do NOT look for these): `worker/libs/pipeline/engine.py` (StageEngine shim),
`orchestrator/{core.py (StageEngine), s012_runner.py, s012_params.py, s456_runner.py,
stage_resolver.py, s6_builder.py}`; `assembly/resolved.py` (`ResolvedStages`); `ProviderRegistry.
build_stages` + `build_enrich_and_chunk_stages`; the `PIPELINE_DYNAMIC_STAGES` env flag (base_config
+ .env + .env.example). The worker always builds `DynamicStageEngine`.

KEPT + reused by the dynamic engine (in `worker/libs/pipeline/orchestrator/`): `cache_io.py` +
`cache_codec.py` + `cache_encoder.py` (node-cache S3 codec, via `CacheDispatch`), `deps.py`
(`StageDeps` legacy container, fed to `WorkerEngineHooks`), `result.py` (`EngineResult`),
`s012_persist.py` (`persist_s012`/`mark_done`/`mark_failed`), `trace_flush.py`. KEPT on
`ProviderRegistry`: the inner builders `_build_parser_chain`/`_build_s2`/`_build_metagen`/
`_build_embed_chain` + `ChunkStageAssembler` (the dynamic assembler reuses them).

Test coverage migrated: legacy `S456Runner`/`StageEngine` fail-closed tests → `test_dynamic_engine.py`
(engine loop) + `test_dynamic_worker_hooks.py` (prepare missing-original fail-closed, collection gate
PG-only, collection-set-no-S6 raise, mark_done/failed). `test_pipeline_fail_closed.py` kept only its
embedder + provider-reraise tests. `test_build_pipeline_parity.py` now compares against the inner
builders directly (not the removed `build_stages`).

## PR-1 file map (all under `common_libs/pipeline/`)

| Concern | Path |
|---|---|
| Pipeline contract + ENGINE (topo, middleware, ON_ERROR, describe) | `base/pipeline/core.py` (`AbstractPipeline`) + `model.py` (`PipelineSchema`) |
| Stage contract (forced ClassVars, step-iteration template, fingerprint, describe) | `base/stage/core.py` (`AbstractStage`) + `model.py` (`StageSchema`, `ErrorPolicy`, `CachePolicy`) |
| Step contract + chain-backed step | `base/step/core.py` (`AbstractStep`, `ChainStep`) + `model.py` (`StepSchema`) |
| Typed context accumulator + deps | `stages/context.py` (`PipelineContext`, `StageDeps`) |
| Unified execution trace | `bricks/tracking/` (`ExecutionTrace`, `StageTrace`, `StepTrace`; reuses `providers.chain.ChainAttempt`) |
| 7 ingest adapters (wrap UNCHANGED legacy stages) | `adapters/` (`base.py` `LegacyStageAdapter`, `delegating_step.py`, `s{0,1,2,4,5,5b,6}_*_adapter.py`) |

## Key contract facts (don't re-derive)

- **Forced stage ClassVars** (enforced in `AbstractStage.__init_subclass__`, raises `TypeError`
  if a concrete subclass omits one): `KEY NAME DESCRIPTION AFTER CONFIG CONSUMES PRODUCES
  CACHE_POLICY ON_ERROR`. An intermediate abstract base opts out with
  `class X(AbstractStage, abstract=True)`.
- **Adapter ClassVars mirror today:** keys `ingest→parse→enrich→chunk→contextualize→metagen→
  embed_index` (chained via `AFTER`); `CACHE_POLICY` = NODE_CACHED for ingest/parse/enrich
  (S0/S1/S2), IDEMPOTENT_WRITE for chunk/contextualize/metagen/embed_index (S4/S5/S5b/S6);
  `ON_ERROR=FAIL_DOC` everywhere (current fail-closed).
- **Ordering is by `AFTER` (topological), never numeric** — the user dislikes renumbering.
- **`session` is NOT a context key** — the S6 adapter opens `ctx.deps.postgres.session()` locally.
- **`PipelineContext`** is the single mutable accumulator (replaces the 7 divergent legacy run()
  signatures): s0_result/s1_result/ir/s2_result/chunks/doc_fields/doc_meta/s4..s6_result +
  fingerprints/from_cache/aux (aux holds the `ExecutionTrace`).
- **`ON_ERROR` composes with the Chain gate's `failure_policy`** (two scopes: intra-step provider
  recovery via the gate; stage-scope via `ON_ERROR`). FAIL_DOC propagates; SKIP/DEGRADE continue.
- Env flags gate the DEFAULT pipeline only — per-collection config still drives stages (S5b lesson).

## Parity invariants the adapters must preserve (PR-1 review caught these)

- **S1 fingerprint = its OWN node fp.** Legacy `run_s1` passes `s1_fp` (node_type "s1") to
  `s1.run(fingerprint=…)`, which keys the markdown S3 blob. The parse adapter reads
  `ctx.fingerprints.get(self.KEY)` (== "parse"), NOT the ingest fp. PR-3 middleware must populate
  `ctx.fingerprints["parse"]` before the parse step (it must anyway, for the node-cache check).
- **`doc_meta` is assembled by the METAGEN adapter** (closes the IO graph: S6 CONSUMES it). Same
  merge as legacy `s456_runner`: `{**s0.implicit_meta, language/page_count/n_blocks/n_figures/
  n_tables from IR, **doc_fields, **doc_user_meta}` — **user wins over generated wins over implicit**.
- **NODE_CACHED fingerprint parity:** `AbstractStage.NODE_VERSION` ClassVar (default "1.0", = legacy
  `_S{0,1,2}_NODE_VERSION`) is fed as `code_version` by PR-3. S0/S1/S2 adapters OVERRIDE
  `fingerprint_params()` to surface the legacy `S012ParamHelpers` values (S0 converter name/version,
  S1 `parse_chain.signature()`, S2 `params_for_fingerprint()`) — the inherited step-aggregate `{}`
  would otherwise drop them. Do NOT import `S012ParamHelpers` from worker (layer violation); replicate.

## PR-2 facts (registry + assembler + config shim)

- **Registry** = `assembly/stage_registry.py`: `register_stage` (keyed by `cls.KEY`), `get_stages`,
  `auto_import_stages` (walks `common_libs.pipeline.adapters`), `topo_order`, `validate_wiring`,
  `StageWiringError`, `ROOT_CONTEXT_KEYS`. The 7 adapters carry `@register_stage`.
- **`build_pipeline`** lives in `assembly/stage_assembler.py` (NOT stage_registry — split for the
  200-line rule + to avoid a cycle). It topo-sorts + `validate_wiring`s the registered adapters, then
  builds each INNER legacy stage via the SAME builders (`registry._build_parser_chain/_build_s2/
  _build_metagen/_build_embed_chain`, `ChunkStageAssembler.build_chunk_stage`, `S5ContextualizeStage`)
  and wraps in the adapter. Parity verified (parse/embed chain signatures, S2/S4 fingerprint params).
- **Import-cycle rule:** `assembly/__init__` exports ONLY the stage_registry primitives, NEVER
  `stage_assembler` (it imports the adapters, which import `assembly.stage_registry` for the
  decorator). Import `build_pipeline` from `assembly.stage_assembler` directly.
- **S6 builder can't be reused** (`S6Builder` is in worker = wrong layer): its exact build sequence is
  replicated in `PipelineAssembler._build_s6`. S0's converter is built from `registry._cfg.GOTENBERG_*`
  (S0 is constant, not config-driven). `build_pipeline` OMITS the `embed_index` stage when qdrant /
  chunk_repo is None (mirrors legacy `S6=None` persist-only).
- **Config shim is ADDITIVE, not the full inversion.** Flat fields (`parse/enrich/.../embed/search`)
  stay the CANONICAL Pydantic fields + stored shape (so `config_describer` config_tree paths, the
  frontend, reindex_diff, and every direct-dict reader are untouched — a real inversion to a `stages`
  dict field would make config_tree an opaque node and break discovery). Added: a read-only `stages`
  keyed-view `@property` + `from_dict` reads BOTH old flat and new `{"stages":{...},"search":{}}`
  (un-nests). `to_dict` UNCHANGED (flat). The full inversion belongs to the later UI-driven phase.

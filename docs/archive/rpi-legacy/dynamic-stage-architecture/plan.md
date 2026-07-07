# RPI Implementation Plan — Dynamic self-describing pipeline architecture (FROZEN 2026-06-29)

FEATURE: Re-found the pipeline on a 4-level, self-describing, fully homogeneous architecture
**Pipeline → Stage → Step → Brick**, then ride it for: metagen UX coherence, a chunk-filter stage,
and doc/chunk activation.
PHASE: Implementation — strangler migration, phased, each increment shippable + green.
RESEARCH: `docs/rpi/dynamic-stage-architecture/research.md`. Design discussion converged & approved by
the user 2026-06-29 ("on part là-dessus").

---

## FROZEN ARCHITECTURE

### Principle — fat abstract, thin concrete
All common logic (execution loop, tracking, error policy, caching, `describe()`) lives in the **abstract
classes**, made functional through well-designed contracts. The deeper you go, the more the written code
is specific to the concrete stage/step. Adding a stage = a class that **declares** (steps, IO, error
policy, cache); everything executive is inherited.

### 4 levels, 3 abstract contracts
```
AbstractPipeline ──> AbstractStage ──> AbstractStep (└ ChainStep) ──> Brick (Chain → providers)
```
- **`AbstractPipeline`** (`pipeline/base/pipeline/core.py`) — IS the engine. `run(ctx)`: topo-order
  `STAGES` by `AFTER`; per stage apply the **middleware** (node-cache via `CACHE_POLICY`, fail-closed,
  progress, tracking); on exception apply `stage.ON_ERROR`. `describe()` recurses into stages.
  Concrete (`IngestPipeline`, `SearchPipeline`) declare only their typed context + stage set
  (auto-discovered from the registry filtered by pipeline).
- **`AbstractStage`** (`pipeline/base/stage/core.py`) — `run(ctx)`: iterate `steps`, thread IO, track each
  (`_run_step_tracked`); forced ClassVars `KEY/NAME/DESCRIPTION/AFTER/CONFIG/CONSUMES/PRODUCES/
  CACHE_POLICY/ON_ERROR`; `fingerprint_params()` aggregates steps; `describe()`. Concrete stage declares
  only its `steps` + config.
- **`AbstractStep`** (`pipeline/base/step/core.py`) — `run(ctx)` + `describe()` + IO ClassVars.
  **`ChainStep`** subtype holds a `Chain` brick (provider escalation + gate + budget + call-cache); `run`
  executes the chain; `describe()` emits category + provider choices + each provider's schema.
- **Bricks** — `Chain`/gate/cache/errors/tracking (common) + provider families + filter rules.

### Two helper families on the abstract classes
1. **Unified execution tracking** — `_run_stage_tracked` / `_run_step_tracked` wrap every child run and
   accumulate a **hierarchical trace** (pipeline→stage→step→chain attempt: start/end/duration/provider/
   escalations/error) into ctx. One tracing mechanism for everything; feeds the existing inspect UI.
2. **Declarative error policy** — `ON_ERROR: ErrorPolicy` (`FAIL_DOC` | `SKIP` | `DEGRADE`) is a mandatory
   stage attribute; the common `AbstractPipeline.run()` reads it on exception and acts. **Composes** with
   the Chain's `gate.failure_policy` (intra-step provider recovery) — two scopes, both declarative, zero
   hand-coded error handling in concrete stages.

### Three recovery layers (the mutualized bricks)
`Chain` (try next provider, intra-step) → Stage/Step propagate → `AbstractPipeline` (apply `ON_ERROR`,
mark doc failed). Caching applied once by the pipeline middleware per `CACHE_POLICY`
(`NODE_CACHED` = S0/S1/S2 today; `IDEMPOTENT_WRITE` = S4/S5/S5b/S6).

### Folder organization (depth = scope; repeated `base/`/`bricks/` names are intentional)
```
common_libs/
  pipeline/
    base/
      pipeline/ {core.py: AbstractPipeline, model, params}
      stage/    {core.py: AbstractStage}
      step/     {core.py: AbstractStep / ChainStep}
    bricks/                       # used by BOTH pipelines
      chain/  cache/  errors/  tracking/
      providers/ {base + registry, embed/, rerank/, llm/}   # consumed ONLY at step level
    ingest/
      core.py                     # IngestPipeline(AbstractPipeline)
      stages/
        base/ {stage/, step/}     # IngestStage/IngestStep — specialize the universal contract
        parsing/ {core.py, steps/}   enrich/ chunk/ contextualize/ metagen/ embed_index/ ...
      bricks/                     # ingest-only
        parsers/ ocr/ vlm/ splitter/ chunk_filter/
    search/
      core.py                     # SearchPipeline(AbstractPipeline)
      stages/ base/{stage,step} · query_transform/ · rerank/ · retrieve/ · ...
      bricks/ fusion/ ...
  storage/   domain/   config/    # general infra, used outside pipelines too
```
- **Providers** live in `pipeline/bricks/providers/`, imported ONLY by steps → no layer cycle by
  construction (a cycle would mean the rule was broken). The search query-embedding becomes a *step*, not
  a low-layer import.
- **Layer discipline**: abstract contracts in `pipeline/base/` are dependency-free of concrete stages.

### Self-describing API (the payoff)
`GET /discovery` = `pipeline.describe()` descending recursively: pipeline → stages → steps → chain →
providers + schemas. **100% backend-generated; UI renders recursively; zero hardcoded text.** Adding a
stage/step/provider surfaces automatically in API + UI.

### Maps onto today (proof it fits)
Ingest: ingest(convert·hash·store) · parse(`chain[docling,mineru,tika]`) · enrich(classify·ocr·vlm·chart,
each a chain) · chunk(split) · contextualize(pure-logic step) · metagen(gen-chunk·gen-doc) ·
embed_index(embed·index — 2 steps). Search: query_transform(rewrite·hyde·multi_query) · rerank(`chain[bge,
cohere]`) · retrieve.

---

## PHASE 1 — Found the architecture (strangler, NO behavior change)

### P1a — Contracts + registry + engine + adapters (logical migration, code stays put)
**New** (`common_libs/pipeline/base/` + `assembly/`):
- `base/pipeline/core.py` `AbstractPipeline` (the engine: topo + middleware + tracking + ON_ERROR +
  describe); `base/stage/core.py` `AbstractStage`; `base/step/core.py` `AbstractStep` + `ChainStep`;
  `base/.../model.py` for `ErrorPolicy`, `CachePolicy`, the describe schemas.
- `pipeline/stages/context.py` `PipelineContext` (typed accumulator + `aux`) + `StageDeps`.
- `bricks/tracking/` (ExecutionTrace collector) — extract/unify the existing chain-trace mechanism.
- `assembly/stage_registry.py` (`@register_stage` + `auto_import` + topo `build_pipeline`, copy of
  `config/pipeline/_registry.py`).
- 7 ingest **adapters** wrapping the existing stage instances (1-step wrap initially) — internals untouched.
- `IngestPipeline` / `SearchPipeline` concrete classes.

**Modified**: `config/pipeline/pipeline.py` (`stages: dict[name,cfg]` keyed map + `from_dict` reads BOTH old
flat blob and new shape + `@property` shims so call sites keep working); `base_config` (+
`PIPELINE_DYNAMIC_STAGES=false`); `worker_bootstrap.py` (build `AbstractPipeline`-driven engine behind flag).

**PR sequence** (each green): PR-1 contracts+context+adapters (unwired) → PR-2 registry+build_pipeline
(parity test vs old resolver) → PR-3 dynamic engine behind flag → PR-4 flip flag, run 780 units + live →
PR-5 delete `resolved.py`/`stage_resolver.py`/`s012_runner.py`/`s456_runner.py`/old `StageEngine`.

### P1b — Physical reorg + step decomposition (one stage at a time, behind the stable contract)
Relocate each stage into `pipeline/ingest/stages/<name>/` + decompose into real steps (e.g. embed_index →
embed-step + index-step; enrich → classify/ocr/vlm/chart steps); move provider families into
`pipeline/bricks/providers/` + `pipeline/ingest/bricks/`; give `search/` the same Stage/Step treatment.
Each stage migration is its own PR with a parity live test.

### Test strategy (P1)
Unit: adapter ctx round-trip; registry topo/cycle/wiring validation; config back-compat (old⇆new);
tracking accumulation; ON_ERROR dispatch (FAIL_DOC/SKIP/DEGRADE). **Live**: `test_dynamic_engine_parity`
— ingest a tiny doc flag OFF vs ON → identical chunk_count/status/payload.
### Agents: **pipeline** (contracts/registry/engine/adapters/reorg) · **test** · **code-reviewer** (parity,
cache_policy mapping, ON_ERROR composition with gate, layer discipline).

---

## PHASE 2 — Backend-driven UI (zero hardcoded text) + metagen coherence
> NOTE (from PR-2): the **full PipelineConfig storage inversion** (flat fields → canonical keyed
> `stages` map) is deferred to HERE, because it changes `to_dict`'s shape which `config_describer`
> walks to build the discovery `config_tree` — so it must migrate together with the describer +
> frontend in this phase. PR-2 made it additive (flat stays canonical; `stages` is a read-only
> keyed-view; `from_dict` already dual-reads the new shape), so this is a clean follow-on, not a redo.
- Backend: each Stage/Step `describe()` emits identity + IO + config schema + (ChainStep) provider
  choices; discovery returns the recursive tree; retire `stage_descriptors.py` literal + flat
  `describe_stages()` + dead `libs.providers.*` import; extend `ui` hints (group/order/help/widget/
  visible_if) + enum value+label + provider `_description`; bring S0 under discovery; **fix metagen field
  dropdown** (object_list `field` node → `kind=enum` from overlay options).
- Frontend: render section descriptions; consume stage descriptors from discovery (retire `stages.ts`/
  `search-stages.ts`); generic `ui_hints`/extra-panel dispatch (kill the `s5b` ID guard); S0 panel reads
  discovery; consolidate `pickerHelpers.ts`; chain/gate copy from `ConfigNode`.
- Tests: unit (describe emits identity; metagen field=enum) + **live** (discovery full identity; dropdown).
- Agents: **backend** · **frontend** · **test** · **code-reviewer** (zero hardcoded text; no special-casing).

---

## PHASE 3 — Chunk-filter stage (parasitic/boilerplate removal)
New ingest stage `after=["chunk"]` (before metagen+embed). Steps = ordered `FilterRule` bricks
(`pipeline/ingest/bricks/chunk_filter/`): layout-label (Docling `PAGE_HEADER/FOOTER`, free) →
cross-page-recurrence (position band ~7% + recurs `≥max(3,0.5×pages)`) → page-number regex → HTML
blocklist (trafilatura/jusText + revert-if->85%). Marks `chunk.active=False` + reason. Optional
DocLayNet ML rule later (never PubLayNet), DeviceManager-gated. Env `CHUNK_FILTER_ENABLED=false` (DEFAULT
pipeline only; per-collection config drives it — the S5b lesson). Tests: per-rule unit + **live**
(running headers come back inactive, excluded from search, metagen skipped them).
Agents: **pipeline** · **test** · **code-reviewer**.

---

## PHASE 4 — Document + chunk activation
Migration: `document.active` + `chunk.active` (bool default true, indexed) + `Chunk.active`. Qdrant: write
`active` into S6 base payload; toggle via existing `set_points_payload` (no re-embed). Search:
`_require_active` filter injected unconditionally (Search-Lab may override). Metagen skips inactive chunks
(filter before gather). Endpoints: doc + chunk active toggles (CONFIG_WRITE). **Reindex-safe** (`active` is
row state, not pipeline/searchable → `reindex_diff` (False,[])). Document-level = primary (stable UUID);
chunk-level = config-stable refinement. Tests: unit (toggle/filter/skip/reindex-safe) + **live**
(deactivate→absent→reactivate→present, no reindex). Agents: **migration-engineer** · **pipeline** ·
**backend** · **frontend** · **test** · **code-reviewer**.

---

## Invariants / cross-phase
IR canonical; provider URL+secret per collection; lean Qdrant payload; collection=contract fail-fast; UI
backend-driven zero hardcoded text; layer DAG respected (abstract contracts dependency-free); double-cache
generalized via `CACHE_POLICY`; env flags gate DEFAULT pipeline only (S5b lesson); every phase ends with
unit **+ one live integration test** (mocked-only missed the S5b wiring bugs). Delivery order P1→P2→P3→P4;
P1 is pure refactor behind a flag with a parity live test as the safety net.

---

**Plan FROZEN per the agreed design. Beginning Phase 1, PR-1 (contracts + adapters, unwired, zero behavior
change). Each PR is independently reviewable + green.**

---
name: dynamic-stage-adapter-parity
description: Parity invariants to enforce when reviewing the dynamic-stage-architecture refactor (Pipeline→Stage→Step adapters, PR-1..PR-5)
metadata:
  type: feedback
---

When reviewing any PR of the `dynamic-stage-architecture` refactor (`common_libs/pipeline/base/`,
`adapters/`, registry, engine), check these adapter-parity invariants against the legacy
`worker/libs/pipeline/orchestrator/` runners (`s012_runner.py`, `s456_runner.py`, `s012_params.py`):

1. **Stage fingerprint key = the stage's OWN key, not a predecessor.** Legacy S1 calls
   `s1.run(s0, fingerprint=s1_fp)` where `s1_fp` is the *parse* node fingerprint (node_type="s1"),
   NOT the s0/ingest fingerprint. An adapter reading `ctx.fingerprints.get("ingest")` for S1 is a
   parity bug — it must read its own `self.KEY` ("parse"). This breaks the markdown S3 key and the
   PR-4 parity live test. (Found wrong in PR-1; the unit test had codified the wrong behavior too.)
2. **CONSUMES/PRODUCES graph must be closed.** Every key a stage CONSUMES must be PRODUCED by an
   upstream stage. In PR-1 `embed_index` CONSUMES `doc_meta` but no stage PRODUCES it (metagen
   produces `doc_fields`). Legacy `s456` assembles `doc_meta = {implicit_fields, **doc_fields,
   **doc_user_meta}` (user wins). That assembly is orchestrator glue not yet ported — flag that
   doc-scope generated metadata + user meta will be silently dropped until a producing step exists.
3. **CACHE_POLICY mapping:** NODE_CACHED = S0/S1/S2 (Merkle node cache via s012_runner);
   IDEMPOTENT_WRITE = S4/S5/S5b/S6 (PG/Qdrant upsert idempotency). `fingerprint_params()` on an
   adapter currently aggregates to `{stage_key: {}}` because `DelegatingStep` returns `{}` — it does
   NOT carry the legacy `code_version`/NODE_VERSION (s0/s1/s2 = "1.0") nor the per-stage params
   (converter name/version, parse_chain signature, S2 `params_for_fingerprint`). PR-3 cannot
   reproduce exact cache keys until the contract grows a version field + the delegating step carries
   real fingerprint params. The contract shape, not just the wiring, needs this.
4. **ON_ERROR = FAIL_DOC for all 7 ingest stages** (legacy `guarded_run` is fail-closed). Composes
   with the Chain gate's `failure_policy` (intra-step provider recovery) — two orthogonal scopes.
5. **S6 session must be opened locally** (`async with ctx.deps.postgres.session()`), never a ctx key.
6. **Layer DAG:** `base/` contracts must not runtime-import concrete stages. Importing
   `common_libs.providers.chain` from `base/step` is fine (providers = L1, pipeline = L3, downward).
   `stages/context.py` keeps all heavy types under `TYPE_CHECKING`.

**Why:** PR-1 is additive/unwired so these are latent, but they are baked into the foundation
contracts + adapter wiring and are expensive to change once PR-2/PR-3 build on them. The PR-4 parity
live test is the safety net but catches divergence late.
**How to apply:** verify each adapter's `_run_inner` call signature + fingerprint source verbatim
against the matching legacy runner method; trace the CONSUMES/PRODUCES graph for unproduced keys.

---

**PR-2 review (2026-06-29, registry + build_pipeline + back-compat shim) — what was verified GREEN,
and what's left for PR-3:**

- `build_pipeline` inner-stage builds are byte-faithful to the legacy path: ingest = fresh
  `GotenbergConverter(GOTENBERG_URL, GOTENBERG_TIMEOUT_S)` (== worker_bootstrap default S0); parse/enrich/
  chunk/contextualize/metagen reuse `registry._build_parser_chain`/`_build_s2`/`ChunkStageAssembler`/
  `S5ContextualizeStage`/`_build_metagen` exactly as `ProviderRegistry.build_stages`. `_build_s6` replicates
  `S6Builder` registry path verbatim (embed chain via `_build_embed_chain(chain,gate,sparse)`, batch_size
  `getattr(first_spec,"batch_size",32)`, None when qdrant/chunk_repo/chain absent). DO re-check `_build_s6`
  on any S6Builder change — it is a hand copy in `common` (worker can't be imported, layer DAG).
- **Memory invariant #2 RESOLVED in PR-2:** the S5b/metagen adapter now PRODUCES `doc_meta` via
  `_assemble_doc_meta`, which matches legacy `s456_runner._run_s6_and_flush_traces` exactly (order:
  `{**implicit_meta, language, page_count, n_blocks, n_figures, n_tables, **doc_fields, **doc_user_meta}` —
  user wins). CONSUMES/PRODUCES graph is now fully closed from ROOT_CONTEXT_KEYS.
- **fingerprint_params parity verified** for the node-cached stages: S0 adapter == `S012ParamHelpers.s0_params`
  (converter name/version), S1 == `s1_params` (`parse_chain.signature()`; `S1ParseStage.parse_chain` is a
  property aliasing `_parse_chain`), S2 == `s2_params` (`params_for_fingerprint()`). S4/S5/S5b/S6 correctly
  do NOT override (IDEMPOTENT_WRITE, not node-cached) — matches legacy.
- **Still on PR-3's plate (not build_pipeline's job, don't expect it in PR-2):** (a) the node fingerprint
  WRAPPER — legacy applies node_type + a code/NODE_VERSION ("1.0" for s0/s1/s2) around the params dict in
  s012_runner; the adapter `fingerprint_params()` returns only the inner params, so the PR-3 caching
  middleware must add node_type+version to reproduce exact cache keys. (b) S6 RUNTIME gating: build_pipeline
  always includes S6 when qdrant+chunk_repo present (regardless of collection_id), mirroring that legacy
  always BUILDS S6; but legacy `_execute_s456` only INVOKES Qdrant indexing when `collection_id is not None`
  and raises `RuntimeError` if collection_id set but S6 None, else persists chunks PG-only. PR-3's engine
  middleware must reproduce that collection_id gate — the adapter's `_run_inner` passes `collection_name=
  ctx.collection_id` straight through, so the gate has to live in the engine/S6 stage, not the builder.

---

**PR-3 review (dynamic engine behind flag) — two parity-critical bugs the green units + a happy-path
live run will NOT catch. Re-verify both are FIXED before PR-4 flips the flag:**

1. **BLOCKING — node cache NEVER hits in the dynamic engine (ordering inversion).**
   `AbstractPipeline._execute_stage` (base/pipeline/core.py) calls `hooks.before_stage()` BEFORE
   `hooks.cache_load()`. `WorkerEngineHooks.before_stage` calls `node_cache.start()` for every
   NODE_CACHED stage, and `NodeCacheOps.start` (caches/node_cache_ops.py) **deletes ANY prior row
   incl. status='done'** then inserts a fresh 'running' row. So `cache_load`→`node_cache.get` (needs
   status='done') always finds 'running' → MISS → S0/S1/S2 re-run on EVERY re-ingest. Legacy
   `s012_runner` does GET first and calls `start()` (via `guarded_run`) ONLY on a miss. FIX: the
   node 'running' marker must move to the post-miss/pre-run path (a new hook fired in
   `_execute_stage` step 3), not `before_stage`. Mocked units pass because `_RecordingHooks.cache_load`
   returns a pinned bool and never exercises the real start→get interaction.

2. **PARITY-CRITICAL — fingerprint node_type + node-cache node_id drift from legacy.**
   `_stage_fingerprint` uses `node_type=stage.KEY` and the hooks pass `stage.KEY` to
   `node_cache.start/get/fail`. Adapter KEYs are `"ingest"/"parse"/"enrich"` (NOT `"s0"/"s1"/"s2"`),
   so the blake3 hash and the stage_run `node_id` BOTH differ from legacy even though
   `fingerprint_params()` + NODE_VERSION ("1.0") match exactly. Consequences on flip: 100% cold cache
   (every legacy-cached doc re-runs once) + stage_run namespace shift (inspect UI / EngineResult are
   only remapped in `_build_result`, the persisted rows are not). The three adapter `fingerprint_params`
   docstrings CLAIM "reproduces today's node-cache key exactly" — FALSE while node_type=KEY. Either map
   KEY→legacy node_type ("s0"/"s1"/"s2") for both the fingerprint node_type and the node_cache node_id,
   or accept the cache reset + fix the docstrings. (Forward-note #3/PR-2 (a) wanted EXACT reproduction.)

Lower severity (PR-3): (a) chunk_repo=None + collection_id set → dynamic RAISES (build omits embed_index
→ engine.run gate raise) vs legacy silent early-return; unreachable in worker (chunk_repo always set), latent
only. (b) `before_stage` flips doc to 'processing' + records node 'running' even on a cache HIT (legacy only
on miss) — same root cause as bug #1. (c) `on_error` marks the enrich node 'failed' if `persist_s012` (run in
`after_stage`) fails — legacy keeps persist outside the s2 guard. (d) leftover mojibake `â€"` in
config/pipeline/pipeline.py:146. (e) PIPELINE_DYNAMIC_STAGES lives in BaseRuntimeConfig but is worker-only,
and is absent from services/docforge/.env.

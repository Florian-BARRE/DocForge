---
name: search-pipeline
description: The graph-based SEARCH pipeline (second pipeline kind on the same engine) — its packages, the bind() capability seam, and three non-obvious build gotchas
metadata:
  type: project
---

# Search pipeline (Wave 1) — a second pipeline kind on the SAME engine

A retrieval pipeline built on the pure graph engine, sibling to ingestion. Engine/builder/validator/
registry reused verbatim — only families, run-inputs and the default blob differ. Design:
`docs/rpi/search-pipeline/research.md`.

**Packages** (active tree `src/docforge-rework/`):
- Artefacts: `shared/libs/public_models/search/` (QuerySpec, EncodedQuery, CandidateSet,
  ScoredCandidates, RankedHits, SearchResult + value objects Candidate/Hit + run-inputs
  RawQuery/QueryFilters/SearchContract). NOT re-exported from `public_models/__init__` — import from
  `shared_libs.public_models.search`.
- Engine side: `shared/libs/pipelines/search/` — `ports.py` (CollectionReadPort), `pipeline.py`
  (SearchPipeline facade, mirrors IngestPipeline), `nodes/<family>/`.
- Families: `query · encode · retrieve · fuse · rerank · postprocess` + reused `deliver` (kind `hits`).
- Must-have graph (P1 default_blob): `normalize → encode(collection) → retrieve(hybrid) →
  hydrate → deliver(hits)`, linear OnSuccess. Everything else is a `SELECTABLE=False` placeholder
  (never in a built graph, `run()` raises via the shared `nodes/placeholder.py` base).

## Three non-obvious gotchas (cost real debugging time)

1. **`bind()` is a DEAD SEAM — the engine NEVER calls it.** `AbstractNode.bind()` sets
   `self._capabilities`, but `FlowEngine`/`PipelineRunner` never invoke it. The retrieve/hydrate nodes
   read the `CollectionReadPort` via `self._capabilities[COLLECTION_READ_CAPABILITY]`, so **something
   must call `.bind({...})` on the built node instances AFTER `PipelineBuilder.build`, BEFORE
   `FlowEngine.execute`**. Wave 1's test binds by hand walking `group.children`; Wave 2 needs a
   request-context capability resolver to do it for real. See [[flow-engine-stage-ports]].

2. **A run-input CANNOT be a primitive — it must be an Artifact.** Node CONSUMES slots are enforced to
   be `Artifact`/`list[Artifact]` (via `SlotTypes.element`), and the resolver feeds `run_input[field]`
   straight into the typed slot. So `query text`, `top_k`, a `filters` dict cannot be run-inputs
   directly — they are wrapped in `RawQuery`/`QueryFilters` artefacts. `RUN_INPUTS=(query, filters,
   contract)` are Artifact-typed IoSlots, not raw values.

3. **`public_models` must NOT import upward from `pipelines`.** The locked contract asked for
   `ScoredCandidates(Artifact, ScoredOutput)`, but `ScoredOutput` lives in `pipelines.base.io`
   (which imports `NodeConfig` FROM public_models) — subclassing it in public_models is an upward
   dependency / layering break. Resolution: `ScoredCandidates` is a plain `Artifact` carrying its own
   aggregate `score` field; the SCORED-ness that enables `ScoreBelow` is delivered at the rerank
   NODE's Produces face (which subclasses `ScoredOutput`, in the pipelines layer). The engine's
   `ScoreBelow` checks the node OUTPUT is `ScoredOutput`, not the artefact — so this is correct, not a
   workaround.

## Encode node = QueryEmbedder as a graph node

`(encode, collection)` rebuilds the collection's OWN embedder from the run-input `SearchContract`
(`embed_kind` + `embed_config` → `NodeRegistry.get("embed", kind)` + `Config(**config)`, extra=forbid
so a drifted blob fails loudly) and drives its `_embed_dense/_embed_sparse/_embed_colbert` hooks on the
one-element query batch — mirrors `app/backend/routers/search/embedder.py`. Provider HTTP in-node is
allowed (same category as the ingest embed node). Encode is LOCKED single-kind (shared vector space),
`UNIQUE_IN_GRAPH=True`.

## Wave 2 (backend) — DONE, live-verified, committed (078984d)

Delivered: `pipeline_registry.PipelineRegistry` (key→facade; the router iterates it, so `/pipelines`
serves ingest + search, `/pipelines/{key}` each; ingest URLs byte-identical). App-side `SearchRunner`
(`app/backend/libs/search/runner.py`): build→validate→**bind port onto children**→`FlowEngine.execute`
→assert SearchResult. `CollectionReadPortImpl` over `search_facade.hybrid` (disabled-exclusion baked in,
unbypassable). `SearchService` wires it from the collection's OWN INGEST embedder (`collection.pipeline`,
NEVER `collection.search` — that's a retrieval-tuning blob, wrong embedder → queries encode into a
different space). `documents_facade.get_chunks_by_ids` = bulk read-only hydration.

**LIVE PARITY PROVEN**: the graph returns byte-identical hits+scores to the facade endpoint on the
default path; ColBERT late-interaction re-scores correctly through the nodes. `SearchService.search(
collection_id, query, top_k=, use_late_interaction=)` is the invocation seam (endpoint NOT cut over yet).

**bind() walk must cover ForEach bodies** (fixed): the runner's walk recurses into `Group` AND
`ForEach.body` (both Groups) — a port-backed node inside a ForEach (future multi-query graph) would
otherwise run unbound and raise at first read. The engine does NOT bind; nothing structurally guards it.
NOTE: `SearchRunner` has NO unit-test home — the conftest deliberately omits the app `backend` root
(app/worker top-level `backend` namespace collision), so app-side search tests go through the HTTP
`client` fixture, never `from backend...`. The ForEach fix is covered by an in-container check, not pytest.

## Code-review backlog — deferred to the endpoint CUTOVER (graph is headless-only today)

- **Palette leak (MEDIUM)**: `deliver` is one global family; ingest's `bundle` and search's `hits` both
  register under it and both are selectable, so each pipeline's palette shows the other's terminal.
  Scope kinds per pipeline kind before any UI consumes the search palette.
- **Double hydration (MEDIUM) → FIXED**: extracted `SearchFacade.hybrid_ids` (lean `(chunk_id, score)`
  retrieval — the collection_exists short-circuit + the `enabled=False`/disabled-doc `must_not`
  exclusion + `QdrantSearchApi.hybrid`, NO Postgres hydration); `hybrid` now calls it and only adds the
  hydration step (exclusion invariant lives in ONE place). The port builds `Candidate`s straight from
  the tuples — the pool is hydrated exactly once, by the hydrate node.
- **top_k cut in the hydrate node → DONE (graph parity)**: the default graph now cuts to top_k at
  `hydrate` (`postprocess/hydrate/core.py`). Its Consumes gained `spec: QuerySpec` (bound
  `FromNode("normalize","spec")` in `SearchPipeline.default_blob`); `run()` RANKS the pool by score
  desc, takes `spec.top_k`, then hydrates ONLY that cut set (never the full over-sampled pool).
  `candidate_k` over-sampling in `normalize` STAYS (a future rerank consumes the pool) — the cut is at
  hydrate only. Fewer-than-top_k possible (a cut candidate whose row vanished is dropped, same as the
  facade path). Live parity re-proven: top_k=10 returns exactly the 10 endpoint hits, same order.
- **Metadata parity (LOW)**: verify delivered `Hit.metadata` vs the live SearchResponse before cutover.

## Product finding — enable/disable payload migration gap → FIXED (5776654)

Was: `search_facade.hybrid` added a positive `Match(enabled=True)`, which Qdrant matches only on
points that CARRY the flag. Points ingested BEFORE the enable/disable payload write have no `enabled`
field → **every search returned 0 hits** on pre-migration collections (observed: DemoCollection, and
two colbert collections with EMPTY payload from a pre-fix partial run).

Fixed migration-free by INVERTING the guard: the enabled flag moved from a `must` condition to a
`must_not` exclusion `Match(enabled=False)` (alongside the disabled-document `MatchAny`). A point with
no flag is not matched by `enabled=False` → stays searchable (default-enabled); only an explicit
`enabled=False` (disabled chunk / boilerplate role) is dropped. Self-healing, no Qdrant backfill.
Live-verified: DemoCollection 0 → 62 hits. Rule if you ever re-touch this: **never require
`enabled=True` positively** — legacy payloads lack the field. Exclude the negative instead.

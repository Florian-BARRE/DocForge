# RPI Research/Design — Graph-based SEARCH pipeline on the DocForge engine

FEATURE: a composable, discovery-driven **retrieval pipeline** built on the SAME pure-graph engine as
ingestion, with custom search node families — the analog of the 7-stage ingestion pipeline. Anticipates
the search stages/options up front (future stages scaffolded as `SELECTABLE=False` placeholders).
ACTIVE TREE: `src/docforge-rework/`. Grounded by 2 agents (pipeline = engine/taxonomy, backend = current
internals). No code written.

---

## Load-bearing facts (both agents)

- **The engine hardcodes nothing about ingestion.** `FlowEngine.execute(group, run_input: dict, …)`
  (`engine/core.py:435`) takes a plain dict addressable by `FromRunInput(field)`; the walk knows no stage
  order. `PipelineBuilder.build` + `GraphValidator.validate` + `NodeRegistry` + transitions/bindings/ForEach
  + `ChainFragmentBuilder` are all reused **verbatim, zero change**.
- **The engine runs INLINE, synchronous, in the API request** — `FlowEngine.execute` is a pure async class
  with zero arq coupling. Ingestion runs async in the worker; search runs sub-second in-process. This is the
  single most load-bearing fact for the design.
- **The current search path is a direct facade call, NOT a graph** (clean slate; the old
  `SearchPipelineEngine`/`build_search_pipeline` machinery is gone — stale memory corrected).
- **"Zero I/O in a node" is already not literal**: `EmbedBgeServerNode.run()` POSTs to bge_server inside the
  node (`nodes/embed/bge_server/core.py:59-68`). Only WRITES are edge-only; the disabled-chunk exclusion is
  enforced in `search_facade.py:76-83`, not in a node.

---

## (1) Engine reuse + the second-pipeline-kind seam

Reused verbatim: `FlowEngine` (`engine/core.py:435`), `PipelineBuilder` (`build/builder.py:103`),
`GraphValidator` (`validation/validator.py`), `NodeRegistry`+families (`registry.py:84-227`, `catalog()`
already hides `SELECTABLE=False`), transitions/bindings/ForEach, `ChainFragmentBuilder` (`build/chain.py:77`).

Hardcoded to `ingest` → the seam to open:
1. **`IngestPipeline`** (`ingest/pipeline.py:25`) — per-pipeline facade: `FAMILIES`, `RUN_INPUTS`
   (source+contract), `palette()`, `default_blob()`. **Search mirrors it: a `SearchPipeline`** with
   `RUN_INPUTS=(query, filters, contract)`, its own FAMILIES, palette, default_blob.
2. **Pipelines router** (`app/backend/routers/pipelines/router.py:47`) — hardcodes ONE `ingest` surface and
   literally comments *"the search pipeline will join later"*. **Seam: a `PipelineCatalog` registry
   `key → facade class`**; the router iterates it (`/pipelines/{key}/…`). Backend-agent change; blob-as-data
   + `?full` discipline unchanged.
3. **`PipelineRunner`** (`worker/backend/libs/runner/core.py:96,113`) — hardcodes ingest run-input + the
   `RunBundle` output. **NOT reused directly.** Search needs a thin **app-side `SearchRunner`**
   (build→validate→execute→assert `SearchResult`) reusing FlowEngine/Builder/Validator verbatim. Optional:
   extract a shared `BasePipelineRunner`.

Net new: `SearchPipeline` facade + `PipelineCatalog` seam + app-side `SearchRunner` + the search
families/nodes/artefacts below. Engine/registry/build/validation = 0 change.

## (2) Purity/IO — DECISION: vector store as a read-only capability injected via `bind()`

**The precise real node rule (to publish in architecture.md):**
> A node MUST NOT write to or mutate any store (Postgres/Qdrant/S3) and MUST hold no hidden persistent
> state. It MAY call **stateless external capabilities** — model providers (embed/ocr/vlm/llm) **and
> read-only store queries** — as long as the capability is a pure function of `(input, config)` with no
> observable side-effect. Writes/index-mutation stay at the worker edge. Determinism is preserved by
> mocking the capability.

**Decision: option (b) refined by (c).** A `retrieve` node MAY query Qdrant, but the read client arrives
through the **currently-dead `bind()` seam** (`base/node.py:152`, `self._capabilities`) as a
**`CollectionReadPort`** — never by importing a client/facade. Why:
- Same category as the embed node calling bge_server — a stateless read; `QueryEmbedder`
  (`search/embedder.py:44`) already drives a node's provider hooks for search.
- **The disabled-exclusion stays unbypassable**: bake `enabled=True` + the disabled-document `must_not`
  (today `search_facade.py:76-83`) **into the port**, so no composed graph can fetch a disabled point.
  This is why injection beats config-constructing a client (a config-built client could omit the filter).
- Reject (a) (retrieval-at-edge defeats the goal — the retrieve step IS the graph). Encode/rerank stay
  provider-call nodes exactly like embed; only the raw store fetch/hydration takes the injected port.
- Activates the dead `bind()` capability seam for the first real consumer.

## (3) Search stage taxonomy (M=must-have-now, F=future SELECTABLE placeholder)

| # | Stage | Family | Kind(s) | Options | M/F | Reuses |
|---|---|---|---|---|---|---|
| 1 | Query intake | `query` | `normalize` | trim/fold, inline-filter split, lang detect | **M** | — |
| | | | `understand` | LLM intent + filter extraction | F | llm·structgen |
| 2 | Query transform | `query` | `rewrite` / `multi` / `hyde` | LLM rewrite; N-variant fan-out via ForEach; hypothetical doc | F | llm + ForEach |
| 3 | Query encode | `encode` | `collection` | collection's OWN embedder; dense always, sparse/colbert per its config | **M** | embed hooks |
| 4 | Retrieve | `retrieve` | `hybrid` | server RRF dense+sparse; over-sample depth; filter conditions; enabled-exclusion (port) | **M** | `CollectionReadPort` (mirrors `search_api.hybrid`) |
| | | | `dense`/`sparse` | per-modality pools (decomposed) | F | port |
| 5 | Fuse | `fuse` | `rrf`/`weighted` | k; weights; dedup (only when retrieve decomposed) | F | — |
| 6 | Rerank | `rerank` | `colbert` | MAX_SIM over pool; `rescore_pool_size` (folds today's colbert path) | **M** | bge_server colbert |
| | | | `cross_encoder`/`llm` | BGE-reranker `/rerank`; LLM listwise — escalation targets | F | bge_server·llm |
| 7 | Post-process | `postprocess` | `hydrate` | fetch rich chunk fields from PG (read port) | **M** | port |
| | | | `dedup_document`/`mmr`/`parent_expand`/`assemble` | one-per-doc; λ diversity; small-to-big; context assembly | F | port·llm |
| 8 | Deliver | `deliver` | `hits` | ranked hits + debug/trace (output contract) | **M** | existing `deliver` family (`bundle/core.py:60`) |

- **Rerank is the home of the fallback-chain machinery**: cheap re-score → `ScoreBelow(t)` → cross_encoder
  → `OnFailure` → llm, converging `FromFirst`, provided each rerank `Produces` subclasses `ScoredOutput`
  (`base/io.py:53`) so `ScoreBelow` is legal.
- `(encode, collection)` and `(deliver, hits)` are `UNIQUE_IN_GRAPH=True`.
- Cheapest posture: normalize is free; encode/colbert/cross_encoder offload to the running bge_server; every
  LLM stage is `F`.

## (4) Artefacts (`public_models/search/`, each subclasses `Artifact`, every slot described)

| Artefact | Slots | Produced→Consumed |
|---|---|---|
| `QuerySpec` | `text`, `filters:dict`, `language?`, `top_k`, `candidate_k`, `flags:dict` | intake/transform → encode, retrieve |
| `EncodedQuery` | `dense`, `sparse?`, `colbert?`, `model` — query mirror of `ChunkVectors` | encode → retrieve, rerank(colbert) |
| `CandidateSet` | `candidates:list[Candidate]` (`{chunk_id, score, source, payload?}`) | retrieve → fuse, rerank |
| `ScoredCandidates` (`ScoredOutput`) | candidates + inherited `score` (aggregate) — enables `ScoreBelow` | fuse/rerank → rerank/postprocess |
| `RankedHits` | `hits:list[Hit]` (`{chunk_id, document_id, score, rank, text?, metadata?}`) | rerank/postprocess → deliver |
| `SearchResult` | `query`, `hits`, `debug?` — terminal output contract (mirror of `RunBundle`) | deliver → `SearchRunner` asserts |

Faces stay `extra="forbid"`. ForEach multi-query fans out `list[QuerySpec]`; body terminals produce the SAME
slot → `items:list`.

## (5) Current search internals → node mapping

`search/router.py` flag resolution → the `SearchRunner` + query-intake node; `QueryEmbedder`
(`search/embedder.py`) → `(encode, collection)`; `search_facade.hybrid` enabled-exclusion (`:76-83`) →
baked into `CollectionReadPort`; `search_api.hybrid` RRF (`:142`) → `(retrieve, hybrid)`; colbert MAX_SIM
re-score (`search_api.py`) → `(rerank, colbert)`; SearchResponse/Hit → `SearchResult`/`RankedHits`. The
per-collection `Collection.search` blob becomes the search pipeline blob (its own default_blob).

## (6) Phased build plan

- **P0 — the seam** (no new nodes): `PipelineCatalog` (key→facade) + refactor `pipelines/router.py` to
  iterate it + `SearchPipeline` skeleton + app-side `SearchRunner`. Prove with a trivial identity graph.
- **P1 — smallest viable graph**: `query(normalize) → encode(collection) → retrieve(hybrid) → deliver(hits)`
  + the 4 artefacts + the injected `CollectionReadPort` (exclusion baked in). Target: **result-parity with
  today's `search/router.py`, expressed as a graph.**
- **P2 — rerank + colbert**: `rerank` family; fold late-interaction into `(rerank, colbert)`; add
  `(rerank, cross_encoder)`; wire `ScoreBelow/OnFailure → FromFirst` via `ChainFragmentBuilder`.
- **P3 — decompose retrieve + fuse**: split `(retrieve, hybrid)` → dense+sparse+`(fuse, rrf)`.
- **P4 — query transforms**: `(query, multi)` ForEach, hyde, rewrite, understand (reuse llm/structgen).
- **P5 — post-process**: dedup_document, mmr, parent_expand (small-to-big), assemble.

Anticipation posture: register the FUTURE families/kinds as `SELECTABLE=False` placeholders early so the
structure is future-ready and discoverable, implementing bodies phase by phase.

## (7) Open questions / risks

1. **`SearchRunner` placement** — app-side vs an extracted shared `BasePipelineRunner`. (Recommend app-side
   first; extract later if worth it.)
2. **Encode is LOCKED, not a swappable provider** — shared vector space is non-negotiable; `(encode,
   collection)` derives the embedder from the collection blob, breaking the "interchangeable provider in the
   palette" symmetry. Needs a stage rule: the encode stage is not user-swappable.
3. **Server-side RRF vs graph-native fuse** — `(retrieve, hybrid)` (one Qdrant call) first; decompose in P3.
4. **`CollectionReadPort` contract + synchronous `bind()` delivery** — port carries the exclusion
   unbypassably; needs a request-context capability resolver (none exists; `bind()` is dead code today).
5. **`ScoreBelow` on rerank** — cross-encoder scores aren't cross-model comparable; the escalation threshold
   needs a defined/calibrated `score`.
6. **Filter validation timing** — today's 422 "not a filterable field" (`search/router.py:94`) must move
   into the query-intake node as a run-time `SearchResult.debug` note, not an HTTP error (blob-as-data).
7. **Search stage-rail deferred** — the ingest stage layer is ingest-coupled; the search graph is
   advanced/headless-only initially (no dedicated stage-rail UI yet).

MIGRATION: none (no schema change; `Collection.search` blob already exists). NEW DEPS: none (reuses engine +
bge_server + existing providers).

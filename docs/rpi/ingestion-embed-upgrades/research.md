# RPI Research Brief — Ingestion embed upgrades (late chunking · ColBERT · table serialization)

FEATURE SET: three ingestion features converging on the chunk → embed → Qdrant path.
ACTIVE TREE: `src/docforge-rework/` ONLY. Researched via 3 parallel agents (pipeline, bge-server, backend).

---

## Executive findings (what changed vs the initial framing)

1. **Table serialization is ALREADY DONE.** Tables are rendered to markdown pipe-tables at chunk
   projection (`chunk/base/passages.py:236-241` → `ChunkerHelpers.render_table`, caption folded,
   `tables_atomic=True`). The embedded text is a clean markdown table, not a raw grid. **No new node,
   no gap.** Only residual: no summarization path for *very large* tables (optional metagen add-on).

2. **Late chunking on BGE-M3 has a MODEL-FIT CATCH.** BGE-M3's dense head uses **CLS pooling**
   (`M3Embedder.DEFAULT_POOLING_METHOD="cls"`), not mean pooling. Jina late chunking mean-pools token
   embeddings per span → those corpus vectors live in a **different subspace** than the CLS-pooled query
   vectors produced by the normal `/embed` path. Naive late chunking can therefore **regress** retrieval
   unless both sides use the same pooling. NOT a free lunch on this model. Requires an eval before commit.

3. **ColBERT is the real build** — cleanest contract, but a **one-way-door** Qdrant schema change and a
   **30–60× storage tier** per content point. Well-scoped, mitigable (int8 quant + on_disk + top-N MAX_SIM
   re-score behind a flag).

**Implication:** a **retrieval eval harness is now a prerequisite**, not a nice-to-have — it is the only way
to validate late-chunking pooling and to prove the ColBERT re-score actually helps before paying its storage.

---

## FEATURE 3 — Table serialization  ·  STATUS: already implemented

- **Current path:** `PassageProjector.__block_text` (`chunk/base/passages.py:236-241`) reads `block.table`,
  calls `ChunkerHelpers.render_table` (`helpers.py:157-168` → `__markdown_grid` `:54-84`): header separator
  when `has_header`, pipe-escaping, ragged-row padding. Config: `include_tables=True`, `tables_atomic=True`
  (`chunk/base/config.py:21-31`). Empty/unstructured table (`block.table is None` / no cells) → contributes
  nothing (correct).
- **No change required.** Any quality tweak (merged/spanning cells, row-header marking) is internal to
  `ChunkerHelpers.__markdown_grid` — pure, no contract change.
- **OPTIONAL add-on — large-table one-line summary at metagen:** slots into existing metagen (prep/chunk.py
  emits one `GenerationRequest` per chunk → structgen → apply merges into `Chunk.generated_meta`), **no new
  node**. CAVEAT: metagen prep loops **all** chunks (`prep/chunk.py:79`) — a `table_summary` field would fire
  gpt-4o-mini on **every body chunk**, not just table chunks. Scoping it needs a `has_table` signal on `Chunk`
  + metagen gating. → propose as a **fast-follow contingent on a chunk-type signal**, NOT bundled here.

---

## FEATURE 1 — Late chunking (Jina)

- **Offsets: DERIVABLE, not blocked.** One ingest run = one document; the full-doc token stream = ordered
  concatenation of enabled chunks' **raw `.text`** (body chunks are ordinal-contiguous, furniture appended
  last). No offset field needed on the `Chunk` artefact.
- **Tokenizer must live server-side.** The chunker counts tokens with tiktoken `cl100k_base`
  (`chunk/base/config.py:17`) — NOT BGE-M3's XLM-RoBERTa tokenizer. Exact per-chunk token spans can only be
  computed with BGE-M3's tokenizer → **boundary + pool computation is a bge_server capability**, the node
  stays pure and tokenizer-agnostic.
- **DECISION — new kind, not a flag.** Add `embed/late_chunking` (KIND `late_chunking`, `UNIQUE_IN_GRAPH`,
  `SELECTABLE`), subclassing `EmbedBgeServerConfig`. Rationale: stage-rail picks one kind per slot (a bool
  wouldn't surface as a method); different batching semantics (one whole-doc call vs `batch_size` slices);
  bge_server-specific (must not appear on the OpenAI-compat provider). Adds config knobs
  `window_overlap_tokens: int=128`, `long_document_mode: {window_slide|per_chunk_fallback}`.
- **Node seam:** add `_embed_dense_document(chunks) -> list[list[float]]` hook on `BaseEmbedderNode`
  (default = current per-batch path); the late kind overrides only that. Reuses the filter-to-enabled +
  assemble loop (`embed/base/node.py:108-145`) unchanged. Sparse stays per-chunk (inherited).
- **bge_server contract — Option B (server-side pooling), recommended:**
  - New route `POST /embed_late_chunks`, request `{"text": str, "spans": [[start,end],...], "truncate": bool}`,
    response `list[list[float]]` (one 1024-dim vector per span, input order). Payload ≈ existing `/embed`.
  - Impl (new `service.py` method, bypasses `encode()`): tokenize once with `return_offsets_mapping=True`
    (fast tokenizer confirmed present), run `self.embed_model.model.model(**inputs).last_hidden_state` once
    (internal attr chain), map each char span → token range, **mean-pool** per range, L2-normalize.
  - Long-doc fallback owned by server: `window_slide` packs chunks into ≤8192-token windows at chunk
    boundaries with overlap; `per_chunk_fallback` degrades to isolated per-chunk. Always returns exactly one
    vector per chunk.
  - **Latency: net WIN** — one forward pass per doc instead of N per-chunk.
- **Persistence: NO change** — still one `ChunkVectors.dense` per chunk (`public_models/embed.py:34`),
  written identically at `translator.py:220`.
- ⚠️ **BLOCKING RISK (R1): CLS-vs-mean pooling mismatch.** Mean-pooled corpus vectors ≠ CLS-pooled query
  vectors' subspace. Must either (i) also mean-pool the QUERY side (`QueryEmbedder`) for self-consistency
  (off BGE-M3's training distribution, but internally coherent), or (ii) empirically validate. **Needs the
  eval harness before shipping.** Do not roll out to the default pipeline blind.
- Open: raw `.text` vs `enriched_text` — late chunking should embed **raw** text (the contextualize prefix
  is a competing neighbor-context mechanism; harmless if left on but redundant).

---

## FEATURE 2 — ColBERT third named vector (`content_colbert`)

Design DECIDED: late-interaction / precision re-score signal behind a flag, content-only, never metadata.

- **Enable (bge_server):** new `encode_colbert()` with `return_colbert_vecs=True`; BGE-M3 derives colbert from
  the SAME forward pass (`colbert_linear(last_hidden_state[:,1:])`, L2-normalized, **1024-dim**, length =
  `attention_mask.sum()-1` tokens). New route `POST /embed_colbert`, response `list[list[list[float]]]`
  (per text → per-token vectors). New 4th `BatchQueueWorker` sharing `_model_lock`.
- **Qdrant schema (one-way door):**
  - Constant: add `VectorNames.CONTENT_COLBERT="content_colbert"` (`qdrant/vectors/names.py:15-20`).
  - Schema: new `QdrantVectorSchema.colbert_config(dim)` → `VectorParams(size=dim, distance=COSINE,
    multivector_config=MultiVectorConfig(comparator=MAX_SIM))` (`vectors/vector_schema.py`), merged into
    `vectors_config` at `collection_api.py:59-63 ensure()`. Content-only: NOT emitted in the per-meta-field
    loop → no `meta_*` collision.
  - `ensure()` is idempotent (create-if-absent) → adding colbert to an existing collection requires
    **drop + recreate + full re-embed**. No in-place schema migration exists (nor should it). Enabling
    colbert must flip `Collection.needs_reindex` (currently only metadata-field diffs flip it —
    `collections_facade.py:137-142` needs to also see a collection-level colbert toggle).
  - **Declare per-collection opt-in at BUILD** (unlike the free unused sparse `content_queries_bm25`, colbert
    costs storage the moment it's declared).
- **Persistence (`worker/backend/libs/persistence/translator.py:207-233`):** new branch after `:223` writes
  `item.colbert` under `CONTENT_COLBERT` on the **content point only**. Requires: `QdrantPoint.multivector:
  dict[str, list[list[float]]]` new field (`qdrant/vectors/point.py` — do NOT overload `dense: dict[str,
  list[float]]`); `ChunkVectors.colbert: list[list[float]] | None` (`public_models/embed.py:21-36`);
  `_to_struct` merges `point.multivector` (`index_api.py:26-32`). Metagen vector-update path
  (`index_api.py:67-87`) must NOT touch colbert. Upsert stays idempotent.
- **Search (`qdrant/apis/search_api.py:56-116 hybrid`):** colbert = **second-stage re-score**, not a fusion
  branch. Current RRF `FusionQuery` over dense+sparse prefetches becomes a nested `Prefetch(..., limit=
  rescore_pool)`; outer `query_points(query=<colbert multivector>, using=CONTENT_COLBERT, limit=limit)`
  applies MAX_SIM over the top-N pool. Triggered by presence of a `colbert` kwarg (None ⇒ current single-stage
  path, byte-identical). Disabled-doc `query_filter` stays on the INNER prefetch (`:89-93`) so re-score never
  resurrects a disabled chunk.
- **Flag surface:** `use_late_interaction: bool=False` + `rescore_pool_size: int~100`. Homes:
  (A) per-collection `Collection.search` JSON blob (untyped today; consider a typed `SearchConfig`);
  (B) per-request `SearchRequest` override (`app/backend/routers/search/models.py:13-39`). Thread
  router→`SearchFacade.hybrid`→`QdrantSearchApi.hybrid`. Query-side colbert from `QueryEmbedder`
  (`search/embedder.py`, add a 3rd return).
- **STORAGE CALLOUT:** ~128 KB/chunk (256 tok × 128-dim fp32 example) ≈ **30× dense**; scales with chunk
  length; MAX_SIM is O(q_tok × d_tok) per candidate → **must** be top-N re-score, never first-stage. Mitigate:
  int8 quantization (÷4) + `on_disk=True` on the colbert VectorParams; bound `rescore_pool_size`.
- Conflicts with "vecteur maigre" invariant #6 unless treated as a dedicated re-score index — the quantized,
  on-disk, content-only, flag-gated design is exactly that.

---

## Cross-cutting prerequisite — RETRIEVAL EVAL HARNESS

Both Feature 1 (pooling risk) and Feature 2 (does re-score help?) are **unverifiable without measurement**.
Need: a small golden query set per a test collection + recall@k / nDCG / MRR, run against the live stack.
This gates the default-on rollout of either feature.

---

## MIGRATION / SCHEMA TOUCHPOINTS

- Postgres/Alembic: **none** for late chunking or table serialization. ColBERT: none in Postgres UNLESS the
  colbert-enabled toggle becomes a typed `Collection` column (vs a `search`-blob key) → then migration-engineer.
- Qdrant: colbert = collection vectors-schema change = **recreate + re-embed** (no Alembic; Qdrant-side).

## PROPOSED IMPLEMENTATION ORDER (revised by findings)

0. **Eval harness** (prerequisite to validate 1 & 2).
1. **Table serialization** — already done; optionally the gated large-table summary (fast-follow, needs
   `has_table` chunk signal). Effectively a no-op / tiny.
2. **Late chunking** — new `embed/late_chunking` kind + `/embed_late_chunks` server route; **validate pooling
   on the harness before default-on**; decide query-side pooling.
3. **ColBERT** — LAST (one-way-door Qdrant schema). bge_server `/embed_colbert` → schema/persistence →
   flag-gated search re-score → UI flag. Quantized + on_disk + top-N.

## OUTCOME (implemented + live-verified, 2026-07-13)

ColBERT SHIPPED. 28 files, +798/-59, 480 unit tests green, code-review APPROVED. Live end-to-end proof:
a collection with `embed_colbert=True` ingested a real docx → Qdrant carries `content_colbert`
(353 token-vecs × 1024 on a chunk point, int8+on_disk+MAX_SIM) → search `use_late_interaction=True`
re-scores (MAX_SIM scores ~6.9 vs RRF ~1.0), `False` path byte-identical. 3/3 ingests reliable.

Two bugs the live test caught (unit tests missed both — fakes were non-empty and tiny):
1. `colbert_dim` derived from the first chunk only → a degenerate leading chunk nulled the axis. Fixed:
   first NON-EMPTY matrix (`embed/base/node.py`).
2. **Qdrant 32 MB `max_request_size`**: full-precision colbert floats make a whole-doc upsert ~36 MB →
   instant 400 + connection reset (looked like a timeout / empty vector; was neither, and INTERMITTENT
   by token count). Fixed: byte-bounded batching (`index_api.upsert`, ~16 MB/request) + client timeout
   5 s→60 s. See code-reviewer memory [[multivector-upsert-byte-limit]].

Two ENVIRONMENTAL findings (NOT colbert, flagged for infra):
- Worker Docker DNS (`127.0.0.11`) has NO external upstream → the whole stack can't reach OpenAI
  (metagen + figure VLM broken for every collection). Real fix = `dns: [8.8.8.8, 1.1.1.1]` on the
  app/worker services in compose (infra domain). Worked around in-memory for the live test only.
- Frontend has NO Search Lab UI at all — the `use_late_interaction` toggle has no screen to live in;
  colbert is driven via the API + per-collection `Collection.search` blob. UI = separate future feature.

Deferred: late chunking (BGE-M3 CLS-vs-mean risk, needs eval); table summary (needs `has_table` gate).

## DECISIONS (user, 2026-07-13)

- **Table serialization** → already implemented; nothing to build. Large-table metagen summary = deferred
  fast-follow (needs a `has_table` chunk signal to gate).
- **Late chunking** → **DEFERRED.** The CLS-vs-mean model-fit risk on BGE-M3 is unresolved without an eval;
  not worth shipping blind. Revisit if/when the eval harness exists.
- **ColBERT** → **BUILD.** Flag lives as keys in the untyped `Collection.search` blob (no migration, no typed
  SearchConfig for now).

## LOCKED SHARED CONTRACT (ColBERT — the symbols all agents must use verbatim)

- **bge_server endpoint:** `POST /embed_colbert`. Request reuses `EmbedRequest` (`inputs: list[str] | str`).
  Response `list[list[list[float]]]` (per input text → list of per-token 1024-dim vectors). Routed through a
  new 4th `BatchQueueWorker` sharing `_model_lock`; `encode_colbert()` in `service.py` with
  `return_colbert_vecs=True`.
- **Artefact (`shared/libs/public_models/embed.py`):** `ChunkVectors.colbert: list[list[float]] | None = None`;
  `ChunkEmbeddings.colbert_dim: int | None = None` (1024 when present).
- **Embed node (`embed/bge_server/core.py` config):** `embed_colbert: bool = False` — the SINGLE source of
  truth that a collection wants colbert. When True: POST enabled chunk texts to `/embed_colbert`, set each
  `ChunkVectors.colbert`, set `ChunkEmbeddings.colbert_dim=1024`. Sparse/dense paths unchanged.
- **Qdrant:** `VectorNames.CONTENT_COLBERT = "content_colbert"`. `QdrantVectorSchema.colbert_config(dim)` →
  `VectorParams(size=dim, distance=COSINE, multivector_config=MultiVectorConfig(comparator=MAX_SIM),
  on_disk=True)` + int8 scalar quantization. `QdrantPoint.multivector: dict[str, list[list[float]]]` (new
  field; do NOT overload `dense`). `collection_api.ensure` merges colbert config **only when `colbert_dim`
  is provided**. `index_api._to_struct` merges `point.multivector`. `translator` writes `item.colbert` under
  `CONTENT_COLBERT` on the **content point only** (never `meta_*`, never the metagen vector-update path).
  `ingestion_facade.index` threads `colbert_dim` from `ChunkEmbeddings` to `ensure`.
- **Search:** `Collection.search` blob keys `use_late_interaction: bool` (default False) + `rescore_pool_size:
  int` (default 100). `SearchRequest` overrides `use_late_interaction: bool | None`, `rescore_pool_size:
  int | None`. `QdrantSearchApi.hybrid` gains `colbert: list[list[float]] | None = None`, `rescore_pool_size:
  int = 100` → when `colbert` is not None, the current RRF fusion becomes a nested `Prefetch(limit=
  rescore_pool_size)` and the outer query is `query=colbert, using=CONTENT_COLBERT, limit=limit` (MAX_SIM
  re-score); `colbert=None` ⇒ byte-identical current path. `SearchFacade.hybrid` threads `colbert`.
  `QueryEmbedder` gains a colbert return (calls `/embed_colbert` for the single query). Router resolves
  effective flag (request override else `collection.search.get(...)`) and only embeds+passes colbert when on.
  The disabled-doc `query_filter` stays on the INNER prefetch.

## OPEN QUESTIONS FOR THE PLAN PHASE

- Late chunking pooling: mean-pool the query side too (self-consistent) vs keep CLS query + eval? (R1)
- ColBERT toggle home: `Collection.search` blob key vs typed column (migration)? `rescore_pool_size` tunable?
- Build the eval harness first (recommended) or ship late-chunking behind a non-default kind and eval after?
- bge_server latent inefficiency (dense+sparse = 2 forward passes today) — fold a one-pass refactor in, or
  leave out of scope?

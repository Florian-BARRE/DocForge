# RPI Research Brief — LLM-generated per-chunk metadata stage

> Feature: during ingestion (not at upload), a configurable LLM step generates, **for each chunk**,
> derived metadata (atomic propositions, keywords, summary, entities…) from a configurable
> provider + prompt + rules + params. Each generated field can optionally become
> filterable / searchable. Provider URL+secret per collection (DB, never `.env`).

---

## FEATURE
LLM chunk-enrichment stage (working name **S5b / "metagen"**).

## STAGES AFFECTED
New stage between **S4 (chunking)** and **S6 (indexing)**. Default placement **S4 → S5 → S5b → S6**
(payload-only fields). If a derived field must influence the embedding vector (e.g. keywords folded
into `embed_text`), it must run **before S5**: `S4 → S5b → S5 → S6`. Also touches S6 payload build,
the field_index, discovery/config, admission/validation, reindex-diff.

---

## CRITICAL UPFRONT FINDINGS (reframe the whole feature)

1. **S5 does NOT use an LLM today.** `s5_contextualize/core.py` is a pure deterministic string
   templater (title + breadcrumb + body), zero provider calls, zero cache. → This must be a **NEW
   stage modeled on S2 enrich**, not an extension of S5.

2. **The only LLM provider family is wired into SEARCH, never ingestion.**
   `providers/llm/openai_compat/provider.py` exposes a single Protocol method
   `LLMProvider.generate(prompt, max_tokens, temperature) -> str` (`llm/base.py:18`). **No
   structured/JSON output, no `response_format`, no tools.** → Protocol must be extended with a
   `generate_json(prompt, schema, ...) -> dict` (OpenAI `response_format={"type":"json_schema"}`).
   This is the biggest provider-layer gap.

3. **There is NO per-chunk custom-field channel today.** `FieldIndexHelpers.resolve_field_text`
   (`search/field_index/helpers.py:103-136`) sources non-system fields **only from document-level
   `doc_meta`** (broadcast identically to every chunk); only 4 chunk-level keys are hardcoded
   (`heading_path/page/block_type/token_count`). The `Chunk` domain model
   (`domain/ir/chunk.py:11-33`) has no derived-metadata dict (`prov` is provenance-only). → The
   headline use case (per-chunk generated values) has **nowhere to live** without new plumbing.
   ⚠️ See OPEN QUESTION 1.

4. **The metadata/search stack is already generic over `metadata_fields`.** A *document-level*
   custom field that lands in `doc_meta` flows end-to-end with ZERO new plumbing: payload promotion,
   vector plan (`derive_vector_plan`), fusion, reindex-diff, discovery filters/weights. The
   filterable/lexical/semantic toggles already exist per field
   (`domain/metadata/meta_field_spec.py:13-33`, `storage/postgres/models/metadata_field.py`).

---

## HOW IT WORKS TODAY (key references)

### Chunk + persistence
- `domain/ir/chunk.py:11-33` — `Chunk` dataclass: `raw_text`, `embed_text` (filled by S5), `prov`
  (provenance only). No derived-meta field.
- `storage/postgres/repositories/chunk_repo.py` — raw SQL, `bulk_insert` with **`ON CONFLICT (id)
  DO NOTHING`** (line 97). ⚠️ Re-deriving metadata for an existing chunk id is **silently dropped**
  on re-ingest unless we either (a) fold enrich config into the `config_hash` feeding the chunk
  UUID v5 (S4 semantics, cleanest) or (b) update-in-place via the reindex delete+re-run path.
- DDL in migration `003_chunks.py`; no ORM model → adding `derived_meta JSONB` (+ GIN) = new
  migration after `008` (migration-engineer).

### Field index / searchable schema
- `domain/metadata/meta_field_spec.py:13-33` — `MetaFieldSpec`: `filterable` / `lexical` (BM25) /
  `semantic` (dense) as 3 independent bools + `field_type` (string/number/date/bool/enum/string[]).
- `search/field_index/helpers.py:69-101` `derive_vector_plan`; `:103-136` `resolve_field_text`.
- `pipeline/stages/s6_embed_index/{core.py,helpers.py}` — `build_payload` promotes only
  `filterable` fields; `_embed_fields` builds `meta_<slug>_dense` / `meta_<slug>_bm25` per
  semantic/lexical field; `ensure_collection` fixes the named-vector schema (recreate=True needed
  to change it → reindex).
- Query path: `backend/libs/search/hybrid/service.py`, live payload patch without re-run:
  `backend/libs/search/metadata_indexer/indexer.py`.

### DAG / stages / cache
- DAG is **hardcoded Python**, not data-driven: `worker/libs/pipeline/orchestrator/core.py:189-259`
  + `s456_runner.py:115-143` (S4→S5→S6). Adding a stage = config sub-model on `PipelineConfig`
  (`config/pipeline/pipeline.py:48-53`) + build in `assembly/registry.py:96-101` + thread through
  `ResolvedStages`/`StageResolver`/`S456Runner`/`StageEngine`.
- Provider chains: `assembly/chain_builders.py` (`Chain[T,R]` + `ChainGateConfig`, the S2 pattern).
- Cache: only **S0/S1/S2** are Merkle-DAG node-cached (`caches/fingerprint.py`). S4/S5/S6 rely on
  Postgres `ON CONFLICT` + Qdrant upsert idempotency. `ProviderCallCache`
  (`caches/provider_cache.py`, `compute_call_fingerprint`) dedupes identical (prompt, content) LLM
  calls across docs — **load-bearing** here given per-chunk calls = thousands/doc.

### Discovery / config UI (generic renderer)
- `routers/discovery/router.py:40-110` → `assembly/config_describer.py` `describe(PipelineConfig)`
  walks the Pydantic JSON schema into `ConfigNode`s (scalar/enum/object/chain/provider_union).
- Provider `Any` / `list[Any]` fields need one entry in `_FIELD_CATEGORY_MAP`
  (`config_describer.py:47-58`) → renders as `provider_union` / `chain` from the registry.
- Secrets auto-masked (`_is_secret_key`).

### Admission / validation
- `config/admission/validator.py` — per-upload fail-fast (format/size/metadata payload).
- `config/validation/validator/metadata_checks.py:33-72` — field name/type/enum coherence at
  config-apply (422). Does **not** validate provider reachability or generated-field/system-field
  name collisions.

### Reindex semantics (confirmed)
- `storage/postgres/repositories/config_repo_helpers.py:100-177` `reindex_diff`. Reindex required
  iff: embedding model changed, OR any `pipeline.*` section except `search` changed, OR a field
  gained/lost `semantic`/`lexical`.
- ✔ Making a generated field searchable (semantic/lexical) → reindex. A *filter-only* toggle does
  **not** (payload-patchable live).
- ✔ Changing the generation prompt lives under `pipeline.metagen` (an indexing section) → triggers
  full pipeline re-run/reindex (correct: generated values change).

---

## NEW FILES NEEDED
- `common/common_libs/pipeline/stages/s5b_metagen/core.py` (+ `result.py`) — the stage (S2 pattern:
  `Chain` over `llm` family + `ChainGateConfig` + budget + `ProviderCallCache`).
- `common/common_libs/config/pipeline/stages/metagen_config.py` — `MetaGenConfig`.

## MODIFIED FILES
- `common/common_libs/config/pipeline/pipeline.py` — add `metagen: MetaGenConfig`.
- `common/common_libs/providers/llm/base.py` + `openai_compat/provider.py` — add structured/JSON gen.
- `common/common_libs/domain/ir/chunk.py` — add per-chunk derived-meta field (if per-chunk; OQ1).
- `common/common_libs/storage/postgres/repositories/chunk_repo.py` — persist derived meta;
  reconcile `ON CONFLICT DO NOTHING`.
- `common/common_libs/search/field_index/helpers.py` — `resolve_field_text` per-chunk source path.
- `common/common_libs/pipeline/stages/s6_embed_index/{core.py,helpers.py}` — per-chunk field payload
  + vectors.
- `common/common_libs/pipeline/assembly/{registry.py,resolved.py,config_describer.py,chain_builders.py}`.
- `worker/libs/pipeline/orchestrator/{core.py,stage_resolver.py,s456_runner.py}` — wire the stage +
  merge generated values before S6.
- `app/backend/routers/discovery/{models.py,router.py}` — new ConfigNode kind(s) for the
  per-generated-field toggles + multiline prompt (no UI primitive today).
- `config/validation/validator/metadata_checks.py` (+ a provider/generated-field coherence check).

## NEW DEPENDENCIES
None expected (HTTP LLM via existing `openai_compat`; JSON schema = OpenAI `response_format`).

## NEW ENV VARS
Mirror S2 enrich gate: `METAGEN_ENABLED` (bool, default false), `METAGEN_MAX_BUDGET_USD`.
(Per-collection provider URL+secret stay in DB, never `.env`.)

## MIGRATION NEEDED
Yes (if per-chunk): `ALTER TABLE chunk ADD COLUMN derived_meta JSONB` (+ GIN index if filterable) —
new migration after `008`. (If document-level only: possibly none — reuses existing `metadata_field`
+ `doc_meta` plumbing.)

---

## KEY CONSTRAINTS
- IR canonical; provider URL+secret per collection in DB (never `.env`).
- Lean Qdrant vector: only filterable fields in payload; rich stays in Postgres.
- Collection = contract: fail-fast validation before any LLM spend.
- Config UI must be **generic / discovery-driven** — no special-casing a stage.
- Per-chunk LLM = thousands of calls/doc → budget gate + concurrency/batching + `ProviderCallCache`
  are mandatory, not optional.
- `LLMProvider` is HTTP-only; **DeviceManager does NOT apply** (no GPU/CPU resolution for a remote
  chat endpoint). The "locality" flag here only selects auth policy + default base_url.

---

## RESOLVED DECISIONS (user, 2026-06-28)
1. **Granularity = HYBRID (per-chunk AND document-level).** Each generated field declares its scope:
   `chunk` (own value per chunk → needs `Chunk.derived_meta` + per-chunk resolve path + per-chunk
   payload/vectors + migration) or `document` (one aggregated value → reuses the existing `doc_meta`
   channel with ~zero new plumbing). Plan must support both scopes coherently.
2. **Declaration = typed field list in the stage config.** `MetaGenConfig` carries a list of
   generated-field definitions, each with: name + type + scope (chunk|document) + extraction
   prompt/rule + the 3 searchable toggles (filterable/lexical/semantic). Needs a NEW generic
   `ConfigNode` kind ("list of field defs") in the describer + frontend renderer (today `list[obj]`
   is non-renderable), and a mechanism to materialize/sync these into `metadata_field` rows so the
   existing index/query/reindex stack picks them up.

## REMAINING OPEN QUESTIONS (for the plan)
3. **Structured output contract.** Confirm JSON-schema `response_format` is acceptable as the
   provider extension (vs tool/function-calling) — affects which OpenAI-compat servers work.
4. **DAG placement default.** Payload-only fields → after S5 (S4→S5→S5b→S6). Any field folded into
   the embed vector → before S5. Decide per-field or stage-global.
5. **Re-derivation / cache.** Fold metagen config into chunk `config_hash` (new chunk ids on config
   change, avoids `ON CONFLICT DO NOTHING` trap) vs update-in-place via reindex path. Recommend the
   former (mirrors S4).

---

## RECOMMENDATION SUMMARY
Build a **new S5b "metagen" stage** modeled on S2 enrich (chain over `llm` family, gate, budget,
provider-call cache), slotted **S4 → S5 → S5b → S6** by default. Extend the `LLMProvider` Protocol
for JSON-schema structured output. Add per-chunk `derived_meta` and a per-chunk resolve path in the
field_index so generated fields can be filterable/searchable through the already-generic S6 + query
stack. Surface config generically via a new ConfigNode kind for the per-field toggles + multiline
prompt. Validate provider + field coherence at config-apply (before spend). Reindex-diff already does
the right thing once the prompt lives under `pipeline.metagen` and toggles under `metadata_fields`.

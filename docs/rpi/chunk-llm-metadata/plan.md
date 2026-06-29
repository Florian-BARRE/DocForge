# RPI Implementation Plan — LLM-generated metadata stage ("S5b metagen")

FEATURE: Configurable LLM enrichment stage that, during ingestion, generates derived metadata
(atomic propositions, keywords, summary, entities…) per chunk and/or per document. Each generated
field is a first-class **collection metadata field** (created in the collection params), optionally
filterable / lexical / semantic, and is populated by the LLM during ingestion.
PHASE: Implementation
RESEARCH: `docs/rpi/chunk-llm-metadata/research.md`

## Resolved decisions (revised after user feedback)
- **Two-step config, separation of concerns.**
  1. **Step 1 — collection metadata params:** the field is *created* like any other metadata field
     (name + type + filterable/lexical/semantic toggles), flagged `origin="generated"`. The
     metadata schema stays the single source of truth for field identity + searchability.
  2. **Step 2 — LLM (metagen) section of the pipeline config:** select the provider, then for each
     **target field** (picked from the generated fields) attach a `prompt`/rule + `scope`.
- **Scope lives in the LLM binding (step 2)**, next to the prompt — it's a generation concern
  (chunk = 1 call/chunk, document = 1 call/doc), not a field-identity concern.
- **Structured output auto-derived from the field's type (+ enum_values).** The declared type *is*
  the control surface for the JSON schema — no separate schema config.
- **Hybrid granularity** preserved via per-target `scope = chunk | document`.

## DAG placement
`S0→S1→S2→S4→S5→**S5b**→S6`. S5b runs after S5 (S5's deterministic `embed_text` untouched; S6 indexes
the generated fields).

## Competitive validation & ideas adopted (benchmark: LlamaIndex / Haystack / Unstructured / Azure AI Search / Weaviate / ES / Vectara / Glean / Cohere)
The two-step model is exactly **Azure AI Search's** proven separation: *produce* (skill/prompt) ≠ *persist*
(index field) ≠ *query behavior* (searchable/filterable/facetable attributes). Their `context + /*`
= our per-target `scope chunk|document`. Concrete ideas folded into this plan:
- **Strict structured output** (OpenAI Structured Outputs rules): the auto-derived JSON schema must be
  root-object, `additionalProperties:false`, every property in `required`, optional via `["T","null"]`
  union, and MUST strip unsupported keywords (`pattern`/`format`/`min*`/`max*`/`default`). One stable
  schema per (collection, scope) so the provider caches the compiled grammar across chunks.
- **Reask loop + graceful degrade** (Instructor / Azure): on JSON/validation failure, append the error
  and retry up to `max_retries`; on final failure keep the chunk, log a warning, leave field empty
  (never fail the doc).
- **One combined call per chunk** for all chunk-scope targets (cheaper, schema cached) — already in the design.
- **Human-declared, typed field names** (vs LlamaIndex's opaque auto-keys / Haystack's untyped
  `expected_keys`) — guaranteed by authoring fields in the metadata schema (step 1).
- **Dry-run preview on a sample chunk** (new) — a low-risk "see what it generates before paying for a
  full ingestion" affordance; big UX win, reuses the existing `ContextualizePreview` skeleton.
- **Cost/volume signalling** (new) — per-chunk generation = thousands of calls/doc; surface an estimate
  + the budget cap in the UI before ingestion.
- *(Deferred, noted)* per-field "embedded into body" visibility (LlamaIndex exclude-lists) — our
  filterable/lexical/semantic tri-axis already covers payload + named-vector inclusion; folding a field
  into `embed_text` would need S5b-before-S5 and is out of v1 scope.

---

## Configuration flow (the mental model)
```
Collection params  ──►  metadata_field rows                LLM / metagen pipeline section
(step 1)                name, type, filterable/             (step 2)
                        lexical/semantic, origin=generated  provider (url+secret per collection)
                                   ▲                          targets: [
                                   └──── referenced by ────────  { field: "<generated field name>",
                                                                   prompt: "<extraction rule>",
                                                                   scope: chunk | document } ... ]
```
- The generated field's **searchable toggles** live ONLY on the `metadata_field` row (step 1).
- The **prompt + scope** live ONLY in `pipeline.metagen.targets` (step 2).
- The **JSON schema** sent to the LLM is built at runtime from each target field's `type`/`enum_values`.

---

## Invariant checklist
- [x] IR canonical — `derived_meta` is a chunk annotation, not a new source of truth.
- [x] Provider behind Protocol — `LLMProvider` extended with `generate_json`; per-collection URL+secret in DB.
- [x] Env flag, disabled by default — `METAGEN_ENABLED=false`; empty `targets` ⇒ no-op.
- [x] Alembic migration — `chunk.derived_meta` + `metadata_field.origin`.
- [x] DAG node — S5b wired through registry/resolved/resolver/runner/engine.
- [x] No Docker/MinIO references.

---

## New files

1. `common/common_libs/config/pipeline/stages/metagen_config.py`
   - `MetaGenTarget(BaseModel)`: `field: str` (references a generated `metadata_field` by name),
     `prompt: str` (`Field(json_schema_extra={"ui": "text"})` multiline hint),
     `scope: Literal["chunk","document"] = "chunk"`.
   - `MetaGenConfig(BaseModel)`: `chain: list[Any]=[]` (llm specs), `targets: list[MetaGenTarget]=[]`
     (empty ⇒ no-op), `gate: ChainGateConfig` (default `failure_policy="continue"`),
     `max_concurrency: int=8`. `@model_validator` coerces `chain` like `QueryTransformConfig`.

2. `common/common_libs/pipeline/stages/s5b_metagen/{__init__.py, core.py, result.py, schema_builder.py}`
   - `S5bMetagenStage(LoggerClass)`: `__init__(llm_chain, targets, field_types, provider_cache,
     max_concurrency, max_budget_usd)` where `field_types: dict[str, MetaFieldSpec]` is the resolved
     type/enum lookup for each target (injected from the collection metadata schema). `async
     run(chunks, ir) -> S5bResult`.
   - `MetagenSchemaBuilder` (static-only, `schema_builder.py`): `build_json_schema(targets, field_types)
     -> dict` — maps each scope-group's target field types → a **strict** JSON object schema
     (string→string, number→number, keyword_list/string[]→array<string>, bool→boolean, date→string,
     enum→string{enum: enum_values}); enforces `additionalProperties:false`, all keys in `required`,
     optionals as `["T","null"]`, and omits unsupported keywords (`pattern`/`format`/`min*`/`max*`/
     `default`). This is the "structured output auto-derived from type", OpenAI-Structured-Outputs-safe.
   - `S5bResult(slots dataclass)`: `chunks, doc_fields: dict, n_generated, est_cost_usd, chain_traces`.
     (No `field_specs` — fields already exist as metadata_field rows.)

3. `common/common_libs/config/validation/validator/metagen_checks.py`
   - `MetagenChecks` (static-only): `check_metagen(doc, stages, issues)` — every `metagen.targets[*]
     .field` must reference an existing `metadata_field` with `origin="generated"`; no duplicate
     target; non-empty prompt; valid scope; **metagen enabled (non-empty targets or chain) but no
     selectable LLM provider → error**; a generated metadata_field with no target prompt → warning.
     Issue shape `{code, severity, field, message}`; errors block 422 before any spend.

4. `common/migrations/versions/009_chunk_derived_meta.py` (migration-engineer)
   - `ALTER TABLE chunk ADD COLUMN derived_meta JSONB NOT NULL DEFAULT '{}'` (+ optional GIN).

5. `common/migrations/versions/010_metadata_field_origin.py` (migration-engineer)
   - `ALTER TABLE metadata_field ADD COLUMN origin VARCHAR(20) NOT NULL DEFAULT 'user'`; backfill
     `is_system=True → 'system'`. ORM `MetadataFieldModel.origin`.

## Modified files

### Provider layer (pipeline)
1. `common/common_libs/providers/llm/base.py` — extend Protocol:
   `generate_json(prompt, schema, max_tokens=512, temperature=0.0) -> dict`.
2. `common/common_libs/providers/llm/openai_compat/provider.py` — impl `generate_json` via
   `response_format={"type":"json_schema","json_schema":{"name","strict":true,"schema"}}`; check the
   `refusal` field; `json.loads` the content; **bounded reask loop** (`max_retries`, append the
   parse/validation error and retry); graceful degrade (return `{}` on final failure, logged). Keep a
   tool-calling fallback path for OpenAI-compatible servers lacking `response_format`.

### Metadata domain + creation (backend + migration-engineer)
3. `common/common_libs/domain/metadata/meta_field_spec.py` — add `origin: Literal["system","user",
   "generated"]="user"` to `MetaFieldSpec`.
4. `.../document_helpers.py` (`ConfigFieldNormalizer.to_dict`) + `config_repo_helpers.py`
   (`build_field`) — thread `origin` through serialize/persist.
5. `app/backend/.../config/validation/document.py` — `merge_metadata_schema` carries `origin` on
   user/generated fields (system fields forced to `origin="system"`). **No materialization step** —
   generated fields are authored directly by the user in the metadata schema.

### Admission (backend)
6. `common/common_libs/config/admission/validator.py` — `AdmissionValidator.validate` must **skip
   `origin="generated"` fields** in the required-field / unknown-field checks at upload time (their
   values are produced by S5b, never uploaded).

### Config + stage wiring (pipeline)
7. `common/common_libs/config/pipeline/pipeline.py` — add `metagen: MetaGenConfig`; env-gate via
   `METAGEN_ENABLED`; thread `METAGEN_MAX_BUDGET_USD`.
8. `common/common_libs/config/pipeline/stages/__init__.py` — export.
9. `common/common_libs/pipeline/assembly/chain_builders.py` — `build_metagen_chain(chain_specs,
   gate_cfg) -> Chain | None` (mirror `build_vlm_chain`). `metagen.chain` renders in the UI via the
   **existing `ChainLadder`** (provider escalation, base_url + masked api_key for free) — zero new
   frontend for provider config.
10. `common/common_libs/pipeline/assembly/registry.py` — build `S5bMetagenStage` in `build_stages` +
    `build_enrich_and_chunk_stages`; pass the resolved `field_types` lookup (built from the
    collection's generated metadata fields); return in `ResolvedStages`.
11. `common/common_libs/pipeline/assembly/resolved.py` — add `s5b: S5bMetagenStage`.
12. `common/common_libs/pipeline/assembly/config_describer.py` — (a) `_field_node` new `object_list`
    branch (generic `list[model]` → recursive `item_schema`); (b) `_scalar_node` reads `prop["ui"]`
    → `type="text"`; (c) `_FIELD_CATEGORY_MAP` += `("MetaGenConfig","llm"): "llm"`.

### Discovery overlay — dynamic target picker (backend)
13. `app/backend/routers/discovery/overlays.py` — overlay the `pipeline.metagen.targets[*].field`
    enum **options** with the collection's `origin="generated"` field names (same overlay pattern as
    per-field weights/filters). Keeps the describer generic; the dropdown options are collection data.
14. `app/backend/routers/discovery/models.py` — `ConfigNode.item_schema: list[ConfigNode]=[]` for
    `kind=object_list`; keep `model_rebuild()`.

### Dry-run preview endpoint (backend) — NEW
14b. `app/backend/routers/collections/metagen/router.py` — `POST /collections/{id}/metagen/preview`
     with `{chunk_id, field_name}` (or sample text): resolves the configured chain + the target's
     prompt/scope/type, runs ONE `generate_json` call, returns the generated value(s) + token/cost
     estimate. `@auto_handle_errors`, `response_model`. Lets the user validate a prompt before paying
     for a full ingestion. Mirrors the read-only inspect routers.

### Orchestrator (worker)
15. `worker/libs/pipeline/orchestrator/stage_resolver.py` — add `S5bMetagenStage` to the tuple +
    return `resolved.s5b`.
16. `worker/libs/pipeline/orchestrator/s456_runner.py` — `run_s456`/`_execute_s456` accept `s5b`;
    call `s5b.run(contextualized_chunks, final_ir)` after S5; merge `s5b_result.doc_fields` into
    `doc_meta` **before** `doc_user_meta` (user wins) at the assembly point (~line 173). No
    `field_specs` merge needed — generated fields are already in `metadata_fields`.
17. `worker/libs/pipeline/orchestrator/core.py` — `StageEngine.__init__`/`run` thread `s5b`.
18. worker `entrypoint.py` + app `backend/context.py` — inject the default `s5b`.

### Domain + persistence (pipeline + migration-engineer)
19. `common/common_libs/domain/ir/chunk.py` — add `derived_meta: dict = field(default_factory=dict)`.
20. `common/common_libs/storage/postgres/repositories/chunk_repo.py` — `bulk_insert`: add
    `derived_meta` (jsonb) and change `ON CONFLICT (id) DO NOTHING` → `DO UPDATE SET derived_meta =
    EXCLUDED.derived_meta, embed_text = EXCLUDED.embed_text`; add `derived_meta` to all SELECTs.
    **(Idempotency-contract shift — flag for code-reviewer; P4 memory documents DO NOTHING.)**

### Search / index (pipeline)
21. `common/common_libs/search/field_index/helpers.py` — `resolve_field_text`: add a
    `chunk.derived_meta` lookup (chunk-scope) ahead of the `doc_meta` fallback (document-scope).
    `build_payload` and `_embed_fields` need **no change** (they route through `resolve_field_text`).

### Validation wiring + reindex (backend)
22. `common/common_libs/config/validation/validator/core.py` — wire `MetagenChecks.check_metagen`
    after `MetadataChecks` (verify `ProviderChecks` covers the metagen llm; add entry if keyed by
    stage name).
23. `common/common_libs/storage/postgres/repositories/config_repo_helpers.py` — **no special
    handling needed.** `reindex_diff` already does the right thing: a `metagen` prompt/scope/target
    change is a non-`search` pipeline section change → reindex (correct, output changes); a generated
    field's searchable toggle change lives on `metadata_field` → searchable-schema diff → reindex;
    a filterable-only toggle → no reindex (matches user-field semantics). **Toggles are no longer
    duplicated in `pipeline.metagen`, so the v1 targeted toggle-strip is dropped — simpler.**

### Frontend (frontend agent) — grounded in existing components
24. Metadata schema editor — `components/pipeline/panels/IngestionConditionsPanel.tsx` (the S0 panel).
    The **Origin column already exists** (`tag-system`/`tag-user`). Add a "Gen." checkbox column →
    `updateUserField(idx,'origin','generated')` + a `tag-llm` pill (~30 lines once the backend
    `ConfigMetaField.origin` field + `npm run gen:types` land). Generated rows keep searchable toggles
    editable (identity) but are visually marked.
25. Generic `object_list` renderer (no stage special-casing):
    - `components/ui/types.ts` — add `'object_list'` to the `ConfigNode.kind` union (1 line).
    - `components/ui/RecursiveFieldRenderer.tsx` — new dispatch branch (~10 lines) → `ObjectListPicker`.
    - `components/ui/pickers/ObjectListPicker.tsx` — NEW repeater (~120 lines) modeled on
      `ChainLadder` minus chain/gate semantics; uses the `renderChildren` render-prop for item params
      (`{field, prompt, scope}`), add/remove rows.
    - `components/ui/FieldInput.tsx` — add a `type === 'text'` branch → existing
      `components/ui/primitives/Textarea.tsx` (~10 lines). Backend must emit `type:"text"` (not `"str"`)
      on the prompt field via the `ui` hint.
26. LLM provider — **no new component**: `metagen.chain` renders via the existing `ChainLadder` /
    `ProviderUnionPicker`; masked-secret round-trip (`••• `→ `stripRedacted` in `api/client.ts`) is
    already correct.
27. Dry-run preview — `components/inspect/MetagenPreview.tsx` (NEW, ~150 lines) modeled on
    `ContextualizePreview` (chunk picker → call the new `/metagen/preview` endpoint → show generated
    value). Show a clear "preview unavailable" empty state if the endpoint/provider isn't configured.
28. Cost/volume + reindex signalling — add an amber `.warning-banner` CSS variant (token-driven, no new
    component) showing estimated calls (`#chunks × #chunk-targets + #doc-targets`) + the budget cap,
    and an honest "changing a prompt or a searchable toggle triggers reprocessing/reindex" note (reuse
    the existing reindex banner pattern). A generated field with no bound prompt shows a
    "generated — no prompt yet" badge (from `MetagenChecks` warning).

## Migration
- `009_chunk_derived_meta` — `chunk.derived_meta JSONB NOT NULL DEFAULT '{}'` (+ GIN if filtering).
- `010_metadata_field_origin` — `metadata_field.origin VARCHAR(20) NOT NULL DEFAULT 'user'` + backfill.

## Env vars
- `METAGEN_ENABLED=false`  # disabled by default
- `METAGEN_MAX_BUDGET_USD=0.0`  # 0 = unlimited; mirror ENRICH_MAX_BUDGET_USD

## Test strategy
- Unit `test_metagen_config.py` — target/chain validation, empty=no-op.
- Unit `test_metagen_schema_builder.py` — type→JSON-schema mapping incl. enum + keyword_list.
- Unit `test_s5b_metagen_stage.py` — mocked `generate_json`: chunk-scope writes `derived_meta`,
  doc-scope returns `doc_fields`; one combined call per chunk for all chunk-scope targets; budget
  short-circuit; cache hit on repeat; graceful degrade on provider error.
- Unit `test_llm_generate_json.py` — `response_format` request shape + `{}` on bad JSON.
- Unit `test_resolve_field_text_chunk_scope.py` — chunk-scope from `derived_meta`, doc-scope from `doc_meta`.
- Unit `test_metagen_checks.py` — target→missing/non-generated field, duplicate, empty prompt, bad
  scope, enabled-no-provider, orphan generated field warning.
- Unit `test_admission_skips_generated.py` — generated field not required at upload.
- Unit `test_reindex_diff.py` (extend) — prompt change ⇒ reindex; semantic toggle on generated field
  ⇒ reindex; filterable-only flip ⇒ NO reindex.
- Unit `test_config_describer.py` (extend) — `object_list` + `item_schema` + `text` ui hint; overlay
  injects target.field options.
- Live (stack up) — doc through S5b with a real generated keyword field; assert payload + filter +
  hybrid hit; `chunk.derived_meta` persisted and refreshed on prompt change re-ingest.

---

## Execution order & agent assignment
1. **migration-engineer** — 009 (`chunk.derived_meta`) + 010 (`metadata_field.origin`) + ORM column.
2. **pipeline** — `generate_json` Protocol+impl; `MetaGenConfig`/`MetaGenTarget`; `MetagenSchemaBuilder`;
   `S5bMetagenStage`+result; `chunk.derived_meta`; `chunk_repo` upsert; `resolve_field_text` chunk
   branch; chain_builders; registry (incl. field_types lookup)/resolved/resolver/runner/engine;
   `config_describer` object_list+ui-hint+category.
3. **backend** — `MetaFieldSpec.origin` (+ `ConfigMetaField.origin`) + threading; admission skip
   generated; `MetagenChecks` + validator wiring; discovery overlay for `targets.field` options;
   `ConfigNode.item_schema`; the `POST /metagen/preview` endpoint.
4. **frontend** — "Generated by LLM" column (origin); generic `object_list` repeater + target dropdown
   + `text` textarea; `MetagenPreview`; cost/reindex `warning-banner`. Run `npm run gen:types` after
   backend lands.
5. **test** — the suite above; `uv run --project common pytest tests/units`.
6. **code-reviewer** — full diff; focus on the `ON CONFLICT DO UPDATE` shift (vs P4 memory) and the
   generic-renderer constraint (no stage special-casing).

## Risks / call-outs
- Per-chunk LLM = potentially thousands of calls/doc → budget gate + `max_concurrency` +
  `ProviderCallCache` are load-bearing. One **combined** structured-output call per chunk (all
  chunk-scope targets in one schema) keeps cost down; the cache key includes the prompt-set hash so
  edits recompute and identical (prompt-set, chunk text) dedupes.
- `ON CONFLICT DO NOTHING → DO UPDATE` is the one idempotency-contract shift (safe superset).
- Dynamic `targets.field` dropdown depends on the discovery overlay; if overlay options are stale the
  field is still validated server-side by `MetagenChecks` (defense in depth).
- Backward compat: empty `MetaGenConfig` + gate off ⇒ identical to today; default factory means
  existing pipeline blobs need no change.

---

**Plan is ready (revised for the two-step config). Respond GO to begin implementation or NO-GO to revise.**

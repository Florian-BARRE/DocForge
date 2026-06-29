---
name: metagen-s5b
description: S5b metagen (LLM per-chunk/-document metadata) review map — invariants verified safe + the two recurring hygiene gaps to recheck
metadata:
  type: project
---

S5b "metagen" feature (LLM-generated metadata at ingestion), reviewed 2026-06-28. New stage runs
S4→S5→**S5b**→S6. Generated fields are authored on the collection metadata schema with
`origin="generated"` (migration 017 adds `metadata_field.origin`); `pipeline.metagen.targets[*]`
binds `{field, prompt, scope}`; the strict JSON schema is auto-derived from each field's declared
type. Chunk-scope values → `chunk.derived_meta` (migration 016, JSONB + GIN); document-scope →
merged into `doc_meta`.

**Verified-safe (do NOT re-flag):**
- `chunk_repo.bulk_insert` switched `ON CONFLICT (id) DO NOTHING` → `DO UPDATE SET derived_meta,
  embed_text` only. Safe superset: id (UUID v5 of doc+blocks+config_hash) + structural columns
  unchanged; re-ingest refreshes the two re-derivable columns. Supersedes the old P4 "DO NOTHING"
  memory. S6 Qdrant upsert is still the indexing idempotency mechanism.
- doc_meta merge order: s5b `doc_fields` merged BEFORE `doc_user_meta` (s456_runner.py) → user wins.
- `resolve_field_text` (field_index/helpers.py) consults `derived_meta` AHEAD of `doc_meta` so a
  chunk-scope value wins over a document-scope broadcast.
- `generate_json` (openai_compat/provider.py) never raises into the stage: HTTP error → `{}`,
  parse/validate fail → bounded reask → `{}`, `response_format`-unsupported → one tool-calling
  fallback. Per-collection url+secret, never `.env`.
- Admission validator exempts `origin=="generated"` from required/type checks AND keeps them in
  `fields` so a stray uploaded value isn't flagged unknown.
- Generic renderer: `config_describer` `object_list`/`item_schema` + FE ObjectListPicker /
  RecursiveFieldRenderer are type-driven; `metagen` appears only in comments. `ConfigNode` model
  has `item_schema` + `extra="allow"` so `/discovery` won't 500 on `kind="object_list"`.

**Recurring gaps to recheck on follow-ups:**
- `METAGEN_ENABLED` (kill-switch) + `METAGEN_MAX_BUDGET_USD` were added to `base_config.py` with
  defaults but were MISSING from `services/docforge/.env` — same env-doc convention gap as
  [[deletion_batch_residue]] (SSE_*/ADMISSION_* are documented there; metagen wasn't).
- Stray `src/docforge/.claude/` agent-memory write — see [[stray_claude_dir_under_src]].
- Nullable enum in `MetagenSchemaBuilder`: type union gets `"null"` but `null` not added to the
  `enum` value list — a strict OpenAI endpoint may reject it (mocked tests don't catch).

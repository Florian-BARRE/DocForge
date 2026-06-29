# RPI Implementation Notes — S5b metagen (LLM-generated metadata)

Status: **DONE** — 780 unit tests green, frontend builds clean, code review APPROVED WITH SUGGESTIONS
(no blocking issues). Disabled by default (`METAGEN_ENABLED=false`; empty config = no-op).

## What shipped
A new ingestion stage **S5b** (S4→S5→**S5b**→S6) that, per chunk and/or per document, calls a
configurable LLM to generate derived metadata. Two-step config model:
1. The field is authored in the collection metadata schema (`origin="generated"`, with its type +
   filterable/lexical/semantic toggles).
2. `pipeline.metagen.targets` binds a provider + per-target `{field, prompt, scope}`. The JSON output
   schema is auto-derived from the field's declared type.

Generated values land in `chunk.derived_meta` (chunk-scope) or `doc_meta` (document-scope) and flow
through the already-generic field_index → S6 payload/vectors → hybrid search. A dry-run preview
endpoint lets users test a prompt on one chunk before a full ingestion.

## File inventory & key decisions
→ `.claude/rules/phases.md` (section "S5b — LLM-generated metadata (metagen)") — full file list +
the 8 key decisions, kept there so it loads with the codebase rules.

## Migrations
- `016_chunk_derived_meta` (down_revision 015) — `chunk.derived_meta JSONB NOT NULL DEFAULT '{}'` + GIN.
- `017_metadata_field_origin` (down_revision 016) — `metadata_field.origin VARCHAR(20) DEFAULT 'user'`,
  backfill `is_system → 'system'`.
> Plan said 009/010; the live head was actually 015, so the migration-engineer renumbered to 016/017
> to avoid a duplicate-revision collision. **Migrations are authored but NOT yet applied** — run
> `docker compose exec docforge sh -c 'cd /app/common && alembic upgrade head'` against the live DB.

## Env vars
`METAGEN_ENABLED=false`, `METAGEN_MAX_BUDGET_USD=0.0` — added to `base_config.py`,
`services/docforge/.env`, and `.env.example`.

## Test result
`uv run --project common pytest tests/units -q` → **780 passed**. New: test_metagen_config,
test_metagen_schema_builder, test_s5b_metagen_stage, test_llm_generate_json,
test_resolve_field_text_chunk_scope, test_metagen_checks, test_admission_skips_generated,
api/collections/metagen/test_metagen_preview (21); extended test_reindex_diff, test_discovery_overlays.

## Review verdict
APPROVED WITH SUGGESTIONS. Should-fix items both **resolved**: (1) stray `src/docforge/.claude/` memory
dir moved to repo-root `.claude/agent-memory/` and deleted; (2) `METAGEN_*` added to the .env files.

## Live end-to-end validation (2026-06-29) — PASSED + 3 bugs fixed
Ran `tests/live_test/test_metagen_live.py` against the full stack with OpenAI `gpt-4o-mini`
(`scope="document"`, one tiny inline HTML doc → **1 LLM call, ~$0.0001**). Both tests PASS:
ingestion → S5b LLM generation → S6 embed/index → searchable + filterable confirmed
(`S5b done: generated=1 doc_targets=1`; generated value present in the Qdrant payload and filterable).

Three real bugs were found ONLY via the live run (all unit-mocked tests were green and missed them):
1. **`worker/libs/pipeline/worker/tasks.py`** — the per-job `metadata_fields` snapshot was a hand-rolled
   dict missing `origin` (and `enum_values`/`required`/`is_system`). S5b's `field_types` keeps only
   `origin=="generated"` fields, so every target was filtered out → stage no-op'd. Fixed by using the
   canonical `MetadataHelpers.schema_field_dicts(...)`.
2. **`common_libs/storage/postgres/repositories/collection_repo.py`** (`create`) — built
   `MetadataFieldModel` inline WITHOUT `origin`, so create-collection always stored `origin="user"`
   (even for system fields, and dropping submitted `"generated"`). The validator passed because it
   checks the submitted doc, not the persisted row. Fixed by passing `origin=...`.
3. **`common_libs/pipeline/assembly/registry.py`** (`_build_metagen`) — `targets` were gated on the
   `METAGEN_ENABLED` env flag (`targets = list(metagen.targets) if enabled else []`) while the chain
   was built unconditionally → a collection that explicitly configured metagen was silently no-op'd
   unless the deployment-wide flag was on. Violates "collection = contract". Fixed: per-collection
   config always drives the stage; `METAGEN_ENABLED` gates the DEFAULT pipeline only
   (`build_default_pipeline`), so the feature works as configured with the flag at its `false` default.

Infra note (not a bug): bge_server runs on CPU in dev → BGE-M3 embed is slow (~44s for 11 long
chunks), so a large doc exceeds the 180s embed timeout. The live test uses a tiny inline doc (1 chunk)
to stay well within it; on the GPU compose profile this is a non-issue.

Units re-verified after the fixes: **780 passed**.

## Open follow-ups (nice-to-have, not blocking)
- Add unit regressions for the 3 live-only bugs: tasks.py uses schema_field_dicts (origin present);
  collection_repo.create persists origin; registry honors per-collection metagen targets regardless
  of METAGEN_ENABLED.
- Apply migrations 016/017 to the live DB (above).
- Nullable-enum schema may omit `null` from the enum value list (low impact).
- Minor `field_types` recompute when the kill-switch is off.
- Reserved chunk-key names (`heading_path`/`page`/`block_type`/`token_count`) shadow same-named
  generated fields in `resolve_field_text` — document or guard at validation if it ever matters.
- Verify behavior end-to-end on the live stack with a real LLM provider (the dry-run preview endpoint
  is the fastest way in).

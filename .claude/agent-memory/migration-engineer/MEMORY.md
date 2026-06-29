# Migration Engineer — Memory Index

Shared Postgres schema for `src/docforge/`. Alembic + SQLAlchemy 2 async (asyncpg). The **app** runs
migrations; the worker never does.

## Layout

- Chain: `common/migrations/versions/00N_name.py` — hand-numbered, linear `down_revision`.
- `common/alembic.ini` + `common/migrations/env.py` (reads DB settings from `base_config`).
- Models: `common_libs/storage/postgres/models/` (base, collection, document, block, chunk via
  chunk_repo, job, config_version, metadata_field, provider_call, stage_run).
- Repos: `common_libs/storage/postgres/repositories/` (collection/document/config/job/block/chunk + helpers).
- Run head: `docker compose exec docforge sh -c 'cd /app/common && alembic upgrade head'`.

## Chain so far (001→017)

| Rev | What |
|---|---|
| 001 | initial schema |
| 002 | GIN indexes |
| 003 | chunks table (+3 indexes) |
| 004 | config versioning |
| 005 | drop max_pages |
| 006 | drop metadata weights |
| 007 | drop language metadata field |
| 008 | chunk parent_id |
| 009 | job observability (worker_id, started_at, finished_at, attempt, current_stage, progress) |
| 010 | collection limits (max_in_flight INT, budget_cap_usd FLOAT, both nullable) |
| 011 | auth tables: app_user, api_key, collection_grant (auth/authz data layer) |
| 012 | drop collection.allowed_providers (dead write-only ARRAY(String), always '{}'; downgrade re-adds NOT NULL default '{}') |
| 013 | drop budget cols: collection.budget_cap_usd (010, nullable Float) + job.budget_spent (001, NOT NULL Float default '0.0'); collection.max_in_flight KEPT |
| 014 | drop provider_call.cost (001, NOT NULL Float default '0.0') — last budget sentinel; downgrade re-adds exact 001 shape (safe on populated table) |
| 015 | keys-only authz: add api_key.permissions (JSONB nullable, NULL=full), DROP collection_grant (destructive); downgrade re-creates 011 grant shape |
| 016 | S5b metagen: chunk.derived_meta JSONB NOT NULL DEFAULT '{}' + GIN ix_chunk_derived_meta (per-chunk LLM-generated metadata; additive/safe) |
| 017 | S5b metagen: metadata_field.origin VARCHAR(20) NOT NULL DEFAULT 'user'; backfill 'system' WHERE is_system=true; is_system KEPT |

## Auth schema (011)

- `app_user`: UUID PK, `username` TEXT unique (ix_app_user_username UNIQUE), `password_hash` TEXT
  (argon2 — repos store the hash, NEVER hash/verify), `role` VARCHAR(16) default `user`, `is_active`
  BOOL default true, `created_at` TZ now().
- `api_key`: UUID PK, `user_id`→app_user CASCADE (indexed), `name`, `key_hash` TEXT (indexed —
  per-request lookup; plaintext NEVER stored), `prefix` (first chars, UI), `created_at`, `last_used_at`
  NULL, `revoked_at` NULL (soft revoke). `get_by_hash` excludes revoked.
- `collection_grant`: GitHub-collaborator model. UUID PK, `user_id`→app_user CASCADE,
  `collection_id`→collection CASCADE, `role` VARCHAR(16) read|write|admin, `granted_by`→app_user
  SET NULL (grant outlives its granter), unique (user_id, collection_id) =
  `uq_collection_grant_user_collection` (backs repo upsert via pg ON CONFLICT), indexed on both FKs.
- Role values are Python `StrEnum`s in `models/auth_enums.py` (UserRole root|user, GrantRole
  read|write|admin); DB columns stay plain VARCHAR(16). Matches codebase: existing role/status cols
  are plain strings with inline value comments — no DB CHECK/enum type.
- `collection_grant` has TWO FKs into app_user (user_id, granted_by) → relationship MUST pin
  `foreign_keys=[user_id]` (model) and `foreign_keys="CollectionGrantModel.user_id"` (app_user side)
  or mapper configuration fails.
- Repos use absolute imports `from common_libs.storage.postgres.models import …` (job_repo style),
  NOT the older relative `from ..models import` (collection_repo style). Both exist; prefer absolute.

## S5b metagen schema (016/017)

- `chunk.derived_meta` (JSONB, NOT NULL, server_default `'{}'`): per-chunk map
  `{generated_field_name: value}` written by S5b for **chunk-scope** targets. Document-scope generated
  values go into `doc_meta`, NOT here. Retrieval reads it via `resolve_field_text` (chunk-scope) ahead
  of the `doc_meta` fallback. GIN index `ix_chunk_derived_meta` for future containment/key filters.
  No ORM model for chunk (raw-SQL `chunk_repo`, pipeline-owned) — derived_meta lives only in the
  migration + domain dataclass `domain/ir/chunk.py` (pipeline adds the field there).
- `metadata_field.origin` VARCHAR(20) NOT NULL DEFAULT `'user'`. Three values:
  `system|user|generated`. **Plain VARCHAR, no DB CHECK/enum** (same convention as role/status cols).
  `is_system` is KEPT (not removed) — origin is additive; backfill set `'system'` WHERE is_system.
  Python side: `MetaFieldSpec.origin` + `ConfigMetaField.origin` are `Literal["system","user",
  "generated"] = "user"`; ORM `MetadataFieldModel.origin` has `default+server_default="user"`;
  `system_fields.py` SYSTEM_METADATA_FIELDS each carry `"origin": "system"`.
- `generated` fields: caller-authored in the metadata schema (searchable toggles live there), values
  produced by S5b at ingestion (referenced by `pipeline.metagen.targets[*].field`). Admission must
  SKIP origin=generated in required/unknown checks (backend); they are never uploaded.

## Rules learned

- Plan revision numbers can be STALE: the plan named these 009/010 (written when head was 008) but
  the live chain head was 015 → authored as 016/017. ALWAYS derive the next number from the actual
  `alembic history`/file list, never trust a plan/doc's hardcoded revision number.
- `alembic history`/`heads` run OFFLINE (no DB) and verify chain linkage from the script files alone —
  use them to confirm a single linear head. CWD must be `common/` (script_location is relative).

- A model edit is incomplete without a paired migration (correct `down_revision`, next `00N_`, English docstring).
- Always write a real `downgrade()`. For drops/renames/type changes, prefer additive → backfill →
  later-drop; state data impact explicitly and flag anything irreversible.
- Per-collection limit columns (010) are a dedicated sub-resource, NOT in the pipeline config blob —
  editing a limit must never trigger reindex semantics. See [[reindex-semantics]] (user memory).

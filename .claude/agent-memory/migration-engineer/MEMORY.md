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

## Chain so far (001→010)

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

## Rules learned

- A model edit is incomplete without a paired migration (correct `down_revision`, next `00N_`, English docstring).
- Always write a real `downgrade()`. For drops/renames/type changes, prefer additive → backfill →
  later-drop; state data impact explicitly and flag anything irreversible.
- Per-collection limit columns (010) are a dedicated sub-resource, NOT in the pipeline config blob —
  editing a limit must never trigger reindex semantics. See [[reindex-semantics]] (user memory).

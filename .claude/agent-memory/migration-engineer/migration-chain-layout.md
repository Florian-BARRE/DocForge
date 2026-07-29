---
name: migration-chain-layout
description: Where the rework Alembic chain actually lives, how to run it, and how the auth tables got seeded
metadata:
  type: reference
---

Active migration chain lives in `shared/migrations/versions/` (relative to `src/docforge-rework/`).
The `alembic.ini` is `src/docforge-rework/shared/alembic.ini` with `script_location = %(here)s/migrations`,
so `here` = `shared/`. A `migrations/` dir exists at the rework root but its `versions/` is **empty** —
do not put revisions there.

Run inside the app container (env.py runs async on asyncpg, no psycopg2 in the runtime image):
`docker compose -f docker-compose.rework.yml exec -T rework_app sh -c 'alembic -c /app/shared/alembic.ini upgrade head'`
(`downgrade -1` to step back). Verify state with `alembic ... current` — the "Running upgrade" log
lines are suppressed by the ini logging config, so `current` before/after is the reliable check.

psql for verification: `docker compose -f docker-compose.rework.yml exec -T rework_postgres sh -c
'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\d <table>"'` (creds come from the container's own env).

Chain as of 2026-07-29: `0d66d7d3c37c` (initial full schema) -> `b50c763f5262` (enable/disable, P2)
-> `c7f2a9e4b1d8` (api_key expiry + last-used). Single linear head.

The auth tables (`api_key`, plus `role`/`is_active` on `app_user`) were seeded **inside the initial
`0d66d7d3c37c` migration**, not a separate auth revision — the auth Lots (git) edited the baseline
before first deploy. So api_key columns present at baseline: user_id, name, key_hash, prefix,
permissions (JSONB), revoked_at + UUIDPrimaryKey/TimestampedMixin.

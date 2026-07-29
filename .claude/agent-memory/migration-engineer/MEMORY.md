# Migration Engineer — Memory Index

Shared Postgres schema for the ACTIVE product `src/docforge-rework/` (being renamed `docforge`).
Alembic + SQLAlchemy 2 async (asyncpg). The **app** runs migrations; the worker never does.

## Layout (rework tree)

- Migrations: `src/docforge-rework/shared/migrations/versions/` (+ `env.py`, `script.py.mako`);
  `alembic.ini` at `src/docforge-rework/shared/` (and a root-level scaffold at
  `src/docforge-rework/`). Revision ids are **hash-based** (e.g. `0d66d7d3c37c`), not hand-numbered
  `00N`. The chain currently collapses the whole schema into one initial revision — the pre-rename
  001→017 chain is dead history (git + `docs/archive/`), not something to extend.
- Tables (SQLAlchemy 2 `Mapped`/`mapped_column`): `shared/libs/services/db/postgresql/tables/`,
  grouped by DOMAIN — `authentication/ blobs/ chunks/ collections/ documents/ ir/ observability/`
  (+ `base.py`). This is the source of the autogenerate target metadata.
- Data access is the `shared_libs.services.db` façade (facades/ + clients postgresql/qdrant/s3) —
  worker persists at the edges; nodes never touch the DB.
- Run head: `docker compose -f docker-compose.rework.yml exec rework_app sh -c 'alembic -c /app/shared/alembic.ini upgrade head'`.
  The **`-c` is required in-container** (cwd is `/app/app`, ini is at `/app/shared/`); `alembic.ini` uses
  `script_location = %(here)s/migrations` (cwd-independent). `env.py` ONLINE mode runs **async over asyncpg**
  (`create_async_engine` + `run_sync`) — the runtime image has NO psycopg2 (dev-only dep); offline `--sql`
  keeps the psycopg2 URL string. Works identically on host (`uv run alembic ...` from `shared/`) and container.
  `alembic history`/`heads` run OFFLINE (no DB) and verify chain linkage from the script files alone.

## Timeless authoring conventions

- A model edit is incomplete without a paired migration (correct `down_revision`, English docstring).
- Derive the next revision id from the actual `alembic history`/file list — never trust a plan/doc's
  hardcoded revision number (they go stale).
- Always write a real `downgrade()`. For drops/renames/type changes prefer additive → backfill →
  later-drop; state data impact explicitly and flag anything irreversible.
- Enums stay plain `VARCHAR` with inline value comments (no DB CHECK / PG enum type) — matches the
  existing role/status/origin columns; the Python side owns the `StrEnum`/`Literal`.
- Multi-FK-into-one-table relationships MUST pin `foreign_keys=[...]` on both sides or mapper config
  fails.
- Per-collection limit/resource columns are dedicated sub-resources, NOT part of the pipeline config
  blob — editing one must never trigger reindex semantics.

## Topic file

- [Migration chain conventions](migration-chain-conventions.md) — how the DocForge Alembic chain is structured: numbering, revision-id style, docstring/data-safety conventions to match.
- [Enable/disable columns](enable-disable-columns.md) — document.enabled, chunk.role, chunk.enabled_override semantics + effective-state formula (the in-container env.py path/psycopg2 bugs are now FIXED — migrations run in-container via async env.py, see Layout above).
- [Migration chain layout](migration-chain-layout.md) — chain lives in shared/migrations, run cmd, current linear head, auth tables seeded in baseline
- [api_key columns](api-key-columns.md) — NULL-means-X semantics of revoked_at/expires_at/last_used_at/permissions

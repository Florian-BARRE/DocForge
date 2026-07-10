---
name: enable-disable-columns
description: Semantics of the reversible enable/disable schema — document.enabled, chunk.role, chunk.enabled_override and how effective state resolves
metadata:
  type: project
---

The reversible enable/disable feature (6 phases; P2 added the schema, rev `b50c763f5262`
on top of `0d66d7d3c37c`) persists a document-level toggle and a chunk-level role + override:

- `document.enabled` — `Boolean NOT NULL DEFAULT true`. Plain user on/off (documents have no
  role). Disabling hides every chunk of the document from retrieval regardless of chunk state.
- `chunk.role` — `VARCHAR(32) NOT NULL DEFAULT 'body'`. The pipeline's structural
  classification, a `ChunkRole` value (`body`/`header_footer`/`toc`/`boilerplate`). P3 populates
  it; existing rows backfilled to `body`.
- `chunk.enabled_override` — `Boolean NULLABLE`. The user's per-chunk manual choice. NULL = no
  override.

**Effective searchable state of a chunk = `enabled_override ?? role_default_enabled(role)`** —
the resolution formula lives downstream (search/read layer, P4+), NOT in the schema. The policy
`role_default_enabled(role)` is defined in `shared/libs/public_models/chunk_role.py` (only `body`
defaults enabled). Document `enabled=false` gates the whole document above this.

**Why `role` is a plain VARCHAR (not `value_enum`/PG enum):** it mirrors `block.block_type` — both
are pipeline-assigned structural labels whose `StrEnum` lives in the pure layer
(`public_models`/IR), kept out of the tables layer so new members need no PG enum ALTER. See
[[migration-chain-conventions]] (enums stay plain VARCHAR).

**Operational note — migrations now run in-container AND on host (the old crashes are fixed).**
Three bugs were resolved: (1) the `parents[4]` `IndexError` — the `.env` load is now guarded by
`if "POSTGRES_DSN" not in os.environ:` so the whole host-only block is skipped in containers (which
inject the DSN); (2) `alembic.ini` uses `script_location = %(here)s/migrations` so it resolves from
any cwd; (3) `env.py` ONLINE mode runs **async over asyncpg** (`create_async_engine` + `run_sync`)
instead of the sync psycopg2 driver that the runtime image doesn't ship. In-container command (the
`-c` is required — cwd is `/app/app`, ini at `/app/shared/`):
`docker compose … exec rework_app sh -c 'alembic -c /app/shared/alembic.ini upgrade head'`. Host still
works via `uv run alembic …` from `src/docforge-rework/shared/` (its `.env` points `POSTGRES_DSN` at
`localhost:10041`, the shared dev postgres).

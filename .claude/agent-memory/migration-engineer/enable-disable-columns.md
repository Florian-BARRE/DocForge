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

**Operational gotcha — run migrations from the HOST, not the container.** The documented
`docker compose … exec rework_app 'alembic upgrade head'` currently CRASHES: `shared/migrations/
env.py` computes the `.env` dir as `Path(__file__).resolve().parents[4]`, which assumes the host
tree depth (`src/docforge-rework/shared/migrations/env.py` → `…/services/docforge-rework`). Inside
the container the tree is shallower (`/app/shared/migrations/env.py`), so `parents[4]` raises
`IndexError`. Until env.py is made container-aware, apply/verify from
`src/docforge-rework/shared/` on the host — the host `services/docforge-rework/.env` already points
`POSTGRES_DSN` at `localhost:10041` (the mapped dev postgres the container shares).

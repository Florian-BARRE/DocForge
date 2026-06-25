---
name: migration-chain-conventions
description: How the DocForge Alembic chain is structured — numbering, revision-id style, docstring/data-safety conventions to match
metadata:
  type: project
---

The shared Postgres migration chain lives in `common/migrations/versions/` as a hand-numbered,
strictly linear chain: `00N_name.py` (001 is the root with `down_revision = None`).

**Why:** Hand-numbering (not Alembic's random hashes) keeps the chain human-readable and the
sequential `00N_` filename prefix == the `revision` string == position in history.

**How to apply when authoring a new migration:**
- Find the current head (the revision no other file lists as its `down_revision`), set the new
  file's `down_revision` to it, and pick the next `00N_` number for both filename and `revision`.
- Two revision-id styles coexist in the chain and both are accepted: bare `revision = "012"` (used
  by 005/006/007/012) and typed `revision: str = "013"` + `from typing import Sequence, Union` with
  `Union[...]` annotations (used by 001-004/008-011). Prefer the typed style for new files — it is
  the more recent convention.
- Docstring format every file follows: one-line summary, then `Revision ID:` / `Revises:` /
  `Create Date:` block, then prose explaining WHY the change exists, then an explicit
  **Data safety:** section stating destructive vs additive, index impact, and exactly how
  `downgrade()` reverses it.
- ALWAYS write a real `downgrade()` (never `pass`). For a drop, the downgrade re-adds the column
  with its EXACT original definition copied from the migration that first created it.
- Verify linearity before declaring done: one root, unique revisions, each `down_revision` points
  to the prior one, exactly one head.

Run head: `docker compose exec docforge sh -c 'cd /app/common && alembic upgrade head'` — the APP
runs migrations, not the worker.

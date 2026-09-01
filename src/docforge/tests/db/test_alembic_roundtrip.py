"""Alembic chain integrity — locks in the bug class that shipped this session: a migration
(b1c7e9a4d2f8) froze the whole up/down chain (its ``downgrade()`` didn't invert its own
``upgrade()``), which nothing caught because no test ever ran the chain end to end.

Two checks, both against a REAL Postgres (DDL, partial indexes, enums don't fake convincingly):

1. ``test_full_chain_round_trips`` — upgrade head -> downgrade base -> upgrade head. Any revision
   whose ``downgrade()`` doesn't cleanly invert its ``upgrade()`` breaks this.
2. ``test_head_schema_has_no_unexpected_drift`` — autogenerate-vs-live-schema diff, ALLOWLISTED for
   the two known, intentional migration-only diffs (see ``_KNOWN_DIFFS``). Anything NOT on the
   allowlist fails the test — that's what would have caught ``jsonb_extract_path_text``-shaped bugs
   where a hand-written migration and the ORM model silently diverge.

Sync test functions on purpose: Alembic's ``env.py`` calls ``asyncio.run(...)`` internally on every
command, which raises ``RuntimeError: asyncio.run() cannot be called from a running event loop`` if
invoked from inside an ``async def`` test (pytest-asyncio's own loop). Plain ``def`` avoids the clash.
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from .conftest import alembic_config, sqlalchemy_dsn

pytestmark = pytest.mark.db

# Diffs that are REAL and INTENTIONAL — the model deliberately doesn't declare them (see the
# comments in document_metadata.py / document.py / job.py). Keyed by a cheap (kind, *names) shape so
# a genuinely new, unreviewed drift still fails loudly instead of being swallowed by a broad except.
_KNOWN_DIFFS: set[tuple[str, ...]] = {
    # Functional/GIN indexes on document_metadata — expression/GIN indexes compare unreliably under
    # --autogenerate, so migration c3e9a1f7d2b4 created them SQL-first and the ORM never declares them.
    ("remove_index", "ix_docmeta_field_value_text"),
    ("remove_index", "ix_docmeta_value_gin"),
    # job token/cost meter columns (f6a3d8b2c1e7): the migration set a server_default=0 so existing
    # rows backfill without a separate UPDATE; the ORM models a Python-side default=0 instead, which
    # autogenerate reads as "the server default should be removed". Both are correct, by design.
    ("modify_default", "job", "total_prompt_tokens"),
    ("modify_default", "job", "total_completion_tokens"),
    ("modify_default", "job", "cost_usd"),
}


def _diff_signature(entry: tuple) -> tuple[str, ...] | None:
    """A (kind, *names) key for one flattened autogenerate diff tuple, or None if unrecognised."""
    kind = entry[0]
    if kind in ("add_index", "remove_index"):
        return (kind, entry[1].name)
    if kind == "modify_default":
        # ('modify_default', schema, table, column, kw, existing_default, new_default)
        return (kind, entry[2], entry[3])
    return None


def _flatten(diffs: list) -> list[tuple]:
    """Autogenerate groups multi-part column alterations as nested lists; flatten to one level."""
    flat: list[tuple] = []
    for entry in diffs:
        if isinstance(entry, list):
            flat.extend(entry)
        else:
            flat.append(entry)
    return flat


def test_full_chain_round_trips(alembic_roundtrip_db: str) -> None:
    """upgrade head -> downgrade base -> upgrade head, each step asserted to succeed cleanly."""
    cfg = alembic_config(alembic_roundtrip_db)

    # 1. Forward through the whole chain from nothing.
    command.upgrade(cfg, "head")

    # 2. Backward through the whole chain to nothing — this is where a broken downgrade() freezes.
    command.downgrade(cfg, "base")

    # 3. Forward again — proves the chain is usable from a clean slate a second time (e.g. a fresh
    #    CI runner), not just resilient to being left mid-chain.
    command.upgrade(cfg, "head")


def test_head_schema_has_no_unexpected_drift(migrated_db_name: str) -> None:
    """The ORM metadata matches the migrated-to-head schema, modulo the known allowlisted diffs."""
    # SQLAlchemy's autogenerate compare needs a SYNC connection; asyncpg has no sync driver, so this
    # one comparison uses psycopg2 (a dev-only dependency — never shipped in a runtime image).
    sync_dsn = sqlalchemy_dsn(migrated_db_name).replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    )
    engine = create_engine(sync_dsn)
    try:
        with engine.connect() as connection:
            diffs = _run_compare(connection)
    finally:
        engine.dispose()

    flat = _flatten(diffs)
    unexpected = [entry for entry in flat if _diff_signature(entry) not in _KNOWN_DIFFS]
    assert not unexpected, (
        f"Unexpected autogenerate drift between the ORM models and the migrated-to-head schema "
        f"(add a migration, or allowlist it in _KNOWN_DIFFS if genuinely intentional): {unexpected}"
    )


def _run_compare(connection: Connection) -> list:
    """Import the ORM metadata (mirrors env.py) and diff it against the live connection."""
    from alembic.migration import MigrationContext  # noqa: PLC0415

    import shared_libs.services.db.postgresql.tables  # noqa: PLC0415,F401 — fills Base.metadata
    from shared_libs.services.db.postgresql.tables.base import Base  # noqa: PLC0415

    context = MigrationContext.configure(
        connection, opts={"compare_type": True, "compare_server_default": True}
    )
    return compare_metadata(context, Base.metadata)

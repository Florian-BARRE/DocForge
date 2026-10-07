# ====== Code Summary ======
# add the collection_alias table (a stable slug → one collection, for keys and app configs)
#
# Revision: b4d9e2a7c6f1
# Revises: a8e3b5d1c9f4
# Created: 2026-10-07 00:00:00.000000
#
# API keys and app configs were bound to a collection UUID, so recreating a collection broke them all.
# A collection alias ("chatmop") names one collection; keys may be scoped to ``alias:<name>`` and every
# collection route accepts the alias in place of the UUID, so a rebuilt collection is switched in by
# re-pointing the alias. Columns:
#   - ``name`` VARCHAR(63) PRIMARY KEY, CHECK-ed against the slug grammar ^[a-z0-9][a-z0-9_-]{0,62}$;
#   - ``collection_id`` UUID → ``collection.id`` ON DELETE RESTRICT (indexed): a targeted collection
#     cannot be deleted until its aliases are moved or removed (the API answers 409 first);
#   - ``created_at`` / ``updated_at`` (server-set).
#
# Data safety: SAFE ONLINE upgrade (a new, empty table). The DOWNGRADE drops the table (its index and
# constraints with it), restoring the previous schema verbatim; every alias is lost — keys scoped to
# ``alias:<name>`` then fail closed (they grant nothing through the vanished alias).

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "b4d9e2a7c6f1"
down_revision = "a8e3b5d1c9f4"
branch_labels = None
depends_on = None

# Names rendered by the schema naming convention — kept identical so autogenerate sees no drift.
_TABLE = "collection_alias"
_IX_NAME = "ix_collection_alias_collection_id"


def upgrade() -> None:
    """Create ``collection_alias`` (slug PK, RESTRICT FK to collection, timestamps) + its FK index."""
    # 1. The table: the slug is the primary key (unique by construction) and CHECK-ed at the DB too.
    op.create_table(
        _TABLE,
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "name ~ '^[a-z0-9][a-z0-9_-]{0,62}$'", name=op.f("ck_collection_alias_name_slug")
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collection.id"],
            name=op.f("fk_collection_alias_collection_id_collection"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_collection_alias")),
    )
    # 2. Index the FK: the RESTRICT check on collection delete and "aliases of X" both look it up.
    op.create_index(_IX_NAME, _TABLE, ["collection_id"])


def downgrade() -> None:
    """Drop the index and the table (restores the previous schema verbatim; aliases are lost)."""
    op.drop_index(_IX_NAME, table_name=_TABLE)
    op.drop_table(_TABLE)

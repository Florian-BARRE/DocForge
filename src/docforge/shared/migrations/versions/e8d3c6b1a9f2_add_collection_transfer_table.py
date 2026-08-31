# ====== Code Summary ======
# add the collection_transfer tracking table (export/import jobs + bundle artifact reference)
#
# Revision: e8d3c6b1a9f2
# Revises: d7f4b2e9a1c6
# Created: 2026-08-31 00:00:00.000000
#
# One row per collection EXPORT or IMPORT job. These operations are collection-level (no document),
# so they cannot ride the document-scoped ``job`` table; this row is their status surface AND (for
# export) the durable bundle artifact reference the download endpoint reads. Mirrors the ORM model
# shared_libs...tables/observability/collection_transfer.py exactly (env.py runs compare_type=True,
# so any type/width/nullability drift would surface on the next --autogenerate).
#
# Enum columns use value_enum = Enum(native_enum=False): rendered as sa.Enum(...) whose VARCHAR width
# is derived from the longest member value (kind: "export"/"import" -> 6; status: "running"/"pending"
# -> 7) and which adds NO CHECK constraint. ``status`` and ``progress`` carry a Python-side default
# in the ORM (default=..., not server_default=...), so this migration emits NO server DEFAULT on them
# to stay drift-free — the default is applied by the app on insert, not by Postgres.
#
# Data safety: SAFE ONLINE, purely additive.
#   - Brand-new table + one plain b-tree index; no data touched, no rewrite, no lock on existing tables.
#   - collection_id FK is ON DELETE SET NULL, so deleting a source collection preserves a finished
#     export's bundle record (the key/size/counts stay readable, only the link is cleared).
#   The downgrade drops the index then the table — fully reversible, but destroys transfer history
#   (acceptable: this is bookkeeping, not source-of-truth document data).

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers used by Alembic.
revision = "e8d3c6b1a9f2"
down_revision = "d7f4b2e9a1c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the collection_transfer table and its collection_id lookup index."""
    # 1. Create the table. Column order mirrors the ORM (class-declared columns first, then the
    #    UUIDPrimaryKey / TimestampedMixin columns) so autogenerate sees no reordering.
    op.create_table(
        "collection_transfer",
        sa.Column(
            "kind",
            sa.Enum("export", "import", name="transferkind", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "running", "done", "failed", name="transferstatus", native_enum=False
            ),
            nullable=False,
        ),
        sa.Column("collection_id", sa.Uuid(), nullable=True),
        sa.Column("collection_name", sa.String(length=255), nullable=True),
        sa.Column("s3_key", sa.String(length=512), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("format_version", sa.Integer(), nullable=True),
        sa.Column("dense_dim", sa.Integer(), nullable=True),
        sa.Column("progress", sa.SmallInteger(), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("counts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collection.id"],
            name=op.f("fk_collection_transfer_collection_id_collection"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_transfer")),
    )

    # 2. Index the FK column (declared index=True on the ORM mapping) for the reaper/list lookups.
    op.create_index(
        op.f("ix_collection_transfer_collection_id"),
        "collection_transfer",
        ["collection_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the collection_transfer index then the table (destroys transfer history)."""
    # 1. Drop the index first, then the table it belongs to.
    op.drop_index(op.f("ix_collection_transfer_collection_id"), table_name="collection_transfer")
    op.drop_table("collection_transfer")

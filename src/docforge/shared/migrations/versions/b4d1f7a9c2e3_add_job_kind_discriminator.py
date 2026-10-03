# ====== Code Summary ======
# add job.kind discriminator (NOT NULL, server_default 'ingest')
#
# Revision: b4d1f7a9c2e3
# Revises: a3f9c2e1d7b4
# Created: 2026-10-03 00:00:00.000000
#
# Adds ``job.kind`` so a job row can declare which kind of work it tracks: an ``ingest`` full
# ingestion run (the only kind until now) or a lighter ``metadata_sync`` side-job. It mirrors
# ``job.status`` exactly: value_enum(native_enum=False), i.e. a plain VARCHAR whose length is derived
# from the longest member value ("metadata_sync" = 13), with NO CHECK constraint (SQLAlchemy's Enum
# defaults create_constraint=False), rendered by autogenerate as
# ``sa.Enum("ingest", "metadata_sync", name="jobkind", native_enum=False)``.
#
# Data safety: SAFE ONLINE. The column is NOT NULL with a server_default of 'ingest', so every
# pre-existing row backfills to ingest automatically (all current jobs ARE ingest runs) with no
# separate UPDATE — on PG16 this uses the fast-default optimisation (no full-table rewrite, no lock
# beyond a brief ACCESS EXCLUSIVE). The server_default is kept as a permanent part of the schema (the
# ORM declares the same ``server_default=text("'ingest'")``), so ``compare_server_default`` sees no
# drift — unlike the token/cost meter columns which model a Python-only default. The downgrade drops
# the column verbatim, restoring the prior ``job`` column shape exactly; it loses only the kind
# discriminator, which has no downstream dependency at the prior schema (everything was ingest).

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "b4d1f7a9c2e3"
down_revision = "a3f9c2e1d7b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the NOT NULL ``job.kind`` discriminator, backfilling existing rows to 'ingest'."""
    op.add_column(
        "job",
        sa.Column(
            "kind",
            sa.Enum("ingest", "metadata_sync", name="jobkind", native_enum=False),
            nullable=False,
            server_default=sa.text("'ingest'"),
        ),
    )


def downgrade() -> None:
    """Drop ``job.kind``, restoring the previous ``job`` column shape exactly."""
    op.drop_column("job", "kind")

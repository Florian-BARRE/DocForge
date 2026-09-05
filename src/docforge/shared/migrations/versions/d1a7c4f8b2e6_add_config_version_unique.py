# ====== Code Summary ======
# add a UNIQUE (collection_id, version) constraint to config_version (with a pre-dedup pass)
#
# Revision: d1a7c4f8b2e6
# Revises: a1e4c7b9f206
# Created: 2026-09-05 00:00:00.000000
#
# The collection config history is an append-only log whose ``version`` is meant to be a gap-free
# per-collection counter. Nothing enforced that at the DB level, so two concurrent config PATCHes
# could both read max(version)=N and both write N+1 — minting DUPLICATE (collection_id, version)
# rows. This adds the missing UNIQUE (collection_id, version) constraint (rendered
# ``uq_config_version_collection_id`` by the schema naming convention) so the DB rejects a duplicate,
# and CollectionsFacade now serializes minting with a FOR UPDATE lock so the violation never fires in
# normal operation.
#
# Data safety: NON-DESTRUCTIVE, but it MUTATES existing data before adding the constraint. Adding the
# UNIQUE constraint straight onto live data that already contains duplicate (collection_id, version)
# rows (from the pre-fix race) would FAIL. So the upgrade first RENUMBERS every collection's history
# into a clean gap-free 1..N sequence, ordered by (version, created_at, id) — this preserves the
# existing relative ordering of the snapshots, keeps EVERY history row (no row is dropped), and only
# rewrites the ``version`` integer of rows whose number actually changes. Version numbers are internal
# labels: there is no foreign key or external reference to (collection_id, version) (the export bundle
# carries the snapshots but import never restores the history), so renumbering is safe. The downgrade
# only drops the constraint — it cannot and does not try to reintroduce the pre-dedup duplicate
# numbering (that information is not recoverable and was a bug), so the renumbering is a one-way,
# intentional normalization. The dedup UPDATE and the ADD CONSTRAINT run in one transaction.

# ====== Third-Party Library Imports ======
from alembic import op

# Revision identifiers used by Alembic.
revision = "d1a7c4f8b2e6"
down_revision = "a1e4c7b9f206"
branch_labels = None
depends_on = None

# The constraint name the schema naming convention (uq_%(table_name)s_%(column_0_name)s) renders for
# UniqueConstraint("collection_id", "version") on config_version — kept identical so autogenerate sees
# no drift against the model.
_UNIQUE_NAME = "uq_config_version_collection_id"


def upgrade() -> None:
    """Renumber any duplicate config versions into a clean per-collection sequence, then add UNIQUE."""
    # 1. De-duplicate FIRST: renumber each collection's snapshots to a gap-free 1..N sequence, keeping
    #    the existing order. Only rows whose version actually changes are rewritten. Without this, the
    #    ADD CONSTRAINT below would fail on any pre-fix duplicate rows.
    op.execute(
        """
        WITH renumbered AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY collection_id
                    ORDER BY version, created_at, id
                ) AS new_version
            FROM config_version
        )
        UPDATE config_version AS cv
        SET version = r.new_version
        FROM renumbered AS r
        WHERE cv.id = r.id
          AND cv.version <> r.new_version
        """
    )

    # 2. Now the data is clean — enforce uniqueness so the race can never persist a duplicate again.
    op.create_unique_constraint(_UNIQUE_NAME, "config_version", ["collection_id", "version"])


def downgrade() -> None:
    """Drop the UNIQUE constraint (the one-way dedup renumbering is intentionally not reverted)."""
    op.drop_constraint(_UNIQUE_NAME, "config_version", type_="unique")

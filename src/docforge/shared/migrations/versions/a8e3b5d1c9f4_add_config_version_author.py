# ====== Code Summary ======
# add the author columns to config_version (who wrote each pipeline/search config version)
#
# Revision: a8e3b5d1c9f4
# Revises: f7c2d9a4b1e5
# Created: 2026-10-07 00:00:00.000000
#
# The config history (one row per config write) recorded WHAT changed but never WHO changed it. This
# adds two nullable columns:
#   - ``author_key_id`` UUID → ``api_key.id`` ON DELETE SET NULL (indexed): the authenticating key;
#   - ``author_label`` VARCHAR(255): a write-time snapshot of the author's name (key name, "root",
#     or "anonymous" when auth is off), so a version keeps naming its author after the key is deleted.
#
# Data safety: SAFE ONLINE upgrade (two nullable columns, an FK and a small index; existing rows keep
# NULL = author unknown). The DOWNGRADE drops the index, the FK and both columns, restoring the
# previous shape verbatim; the recorded authorship is lost (it did not exist before this revision).

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision = "a8e3b5d1c9f4"
down_revision = "f7c2d9a4b1e5"
branch_labels = None
depends_on = None

# Names rendered by the schema naming convention (fk_<table>_<col>_<referred>, ix_<table>_<col>) —
# kept identical so autogenerate sees no drift against the model.
_FK_NAME = "fk_config_version_author_key_id_api_key"
_IX_NAME = "ix_config_version_author_key_id"


def upgrade() -> None:
    """Add ``author_key_id`` (FK SET NULL, indexed) and ``author_label`` to config_version."""
    # 1. The two nullable author columns (existing rows = author unknown).
    op.add_column("config_version", sa.Column("author_key_id", sa.Uuid(), nullable=True))
    op.add_column("config_version", sa.Column("author_label", sa.String(length=255), nullable=True))
    # 2. The live key link: deleting a key keeps the version and its label, only unlinks the id.
    op.create_foreign_key(
        _FK_NAME, "config_version", "api_key", ["author_key_id"], ["id"], ondelete="SET NULL"
    )
    # 3. Index the FK so the SET NULL cascade on key deletion never scans the history.
    op.create_index(_IX_NAME, "config_version", ["author_key_id"])


def downgrade() -> None:
    """Drop the index, the FK and both author columns (restores the previous shape verbatim)."""
    op.drop_index(_IX_NAME, table_name="config_version")
    op.drop_constraint(_FK_NAME, "config_version", type_="foreignkey")
    op.drop_column("config_version", "author_label")
    op.drop_column("config_version", "author_key_id")

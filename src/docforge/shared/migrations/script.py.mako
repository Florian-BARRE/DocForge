# ====== Code Summary ======
# ${message}
#
# Revision: ${up_revision}
# Revises: ${down_revision | comma,n}
# Created: ${create_date}

# ====== Third-Party Library Imports ======
import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

# Revision identifiers used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    """Apply this revision's schema changes."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Revert this revision's schema changes."""
    ${downgrades if downgrades else "pass"}

# ====== Code Summary ======
# Defines the shared SQLAlchemy declarative base for all DocForge ORM models.
# Every model module imports `Base` from here so they all register on the same
# `Base.metadata` — this is essential for cross-table relationships and for
# Alembic autogenerate to discover the complete schema in a single import.

# ====== Third-Party Library Imports ======
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all DocForge ORM models."""

    pass

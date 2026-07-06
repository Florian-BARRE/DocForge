# ====== Code Summary ======
# The declarative base + shared mixins for every DocForge table. A single Base gathers all models
# into ONE MetaData so Alembic autogenerate sees the whole schema at once, and an explicit naming
# convention gives every index/constraint a stable, predictable name across migrations (essential
# for clean, reviewable Alembic diffs). The two mixins factor the columns almost every table shares:
# a UUID primary key and a timezone-aware created_at timestamp.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from enum import StrEnum

# ====== Third-Party Library Imports ======
from sqlalchemy import DateTime, Enum, MetaData, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Stable names for indexes / unique / check / foreign / primary constraints — so Alembic never
# emits a migration just because an auto-generated constraint name drifted.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base — one MetaData for the whole schema, with stable constraint names."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def value_enum(enum_cls: type[StrEnum]) -> Enum:
    """
    The schema-wide column type for a StrEnum: VARCHAR persisting the member VALUES.

    SQLAlchemy's default persists member NAMES ("USER"), which would break every comparison
    against the StrEnum values used across the codebase (and the CHECK constraints written
    against 'user'/'chunk'/…). Every enum column MUST be declared through this helper.

    Args:
        enum_cls (type[StrEnum]): The domain enum backing the column.

    Returns:
        Enum: The configured SQLAlchemy Enum type.
    """
    return Enum(
        enum_cls,
        native_enum=False,
        values_callable=lambda cls: [member.value for member in cls],
    )


class UUIDPrimaryKey:
    """Mixin adding a UUID primary key named ``id`` (application-generated, v4)."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    """Mixin adding a server-set ``created_at`` only — for append-only / log tables."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TimestampedMixin:
    """Mixin adding server-set, timezone-aware ``created_at`` and ``updated_at`` timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


__all__ = [
    "Base",
    "UUIDPrimaryKey",
    "TimestampedMixin",
    "CreatedAtMixin",
    "NAMING_CONVENTION",
    "value_enum",
]

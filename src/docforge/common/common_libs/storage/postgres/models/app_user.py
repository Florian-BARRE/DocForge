# ====== Code Summary ======
# SQLAlchemy ORM model for an application user (authentication identity).
# Stores the argon2 password hash (never plaintext), a global role, and an
# active flag. Holds the single root account; owns API keys (cascade).

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# ====== Local Project Imports ======
from .auth_enums import UserRole
from .base import Base

# Cross-model relationships use string class names resolved by the SQLAlchemy registry;
# imports are type-checking only to avoid runtime circular imports.
if TYPE_CHECKING:
    from .api_key import ApiKeyModel


class AppUserModel(Base):
    """
    Persisted authentication identity.

    One row per user (in the keys-only model this is the single root account). The password is
    stored only as an argon2 hash (this layer never hashes or verifies — it just persists what the
    auth layer produces). ``role`` is the global role (``root`` | ``user``); per-collection
    authorization is no longer a stored role — it is the capability scope carried on API keys.
    """

    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Unique login handle — enforced by a unique index (ix_app_user_username).
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # Argon2 hash of the password — plaintext is NEVER stored.
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Global role: "root" | "user" (values from UserRole). Plain VARCHAR column;
    # the StrEnum is the source of truth for legal values in Python.
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default=UserRole.USER.value
    )
    # Soft-disable flag — an inactive user keeps its rows but cannot authenticate.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships — referenced by string class name, resolved by the SQLAlchemy
    # registry once all model modules are imported in the package __init__.
    api_keys: Mapped[list[ApiKeyModel]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

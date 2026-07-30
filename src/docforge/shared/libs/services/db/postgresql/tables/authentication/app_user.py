# ====== Code Summary ======
# The `app_user` table — an account identity: username, password hash (argon2), global role and
# active flag. In the keys-only model the root user owns the API keys that carry the real access.

# ====== Standard Library Imports ======
from enum import StrEnum

# ====== Third-Party Library Imports ======
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, TimestampedMixin, UUIDPrimaryKey, value_enum


class UserRole(StrEnum):
    """Global role of a user account."""

    ROOT = "root"
    USER = "user"


class AppUser(Base, UUIDPrimaryKey, TimestampedMixin):
    """An account identity."""

    __tablename__ = "app_user"

    username: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        value_enum(UserRole), nullable=False, default=UserRole.USER
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


__all__ = ["AppUser", "UserRole"]

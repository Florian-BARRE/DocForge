# ====== Code Summary ======
# The `api_key` table — a programmatic credential owned by a user. Stored hash-only (the plaintext is
# shown once); `prefix` identifies it in the UI; `permissions` scopes it per-collection per-capability
# (NULL = full access); `revoked_at` is a soft revocation marker; `expires_at` is an optional expiry
# (NULL = never expires); `last_used_at` records the last successful authentication (NULL = never used).

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, TimestampedMixin, UUIDPrimaryKey


class ApiKey(Base, UUIDPrimaryKey, TimestampedMixin):
    """A programmatic credential (hash-only) owned by a user."""

    __tablename__ = "api_key"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    permissions: Mapped[Any | None] = mapped_column(JSONB, nullable=True)  # NULL = full access
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # NULL = never expires
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # last successful authentication (throttled best-effort write); NULL = never used


__all__ = ["ApiKey"]

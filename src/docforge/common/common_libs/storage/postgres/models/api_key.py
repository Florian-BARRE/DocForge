# ====== Code Summary ======
# SQLAlchemy ORM model for a user-owned API key.
# Only the hash of the key is stored (lookup by hash on every request); the plaintext
# key is shown once at creation and never persisted. A short prefix is kept for the UI
# to identify the key. Revocation is soft (revoked_at timestamp).

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# ====== Local Project Imports ======
from .base import Base

# Cross-model relationship uses a string class name resolved by the SQLAlchemy registry;
# the import is type-checking only to avoid a runtime circular import.
if TYPE_CHECKING:
    from .app_user import AppUserModel


class ApiKeyModel(Base):
    """
    A user-owned API key used for programmatic authentication.

    The plaintext key is generated and returned to the caller exactly once at creation;
    only ``key_hash`` is persisted and used for the per-request lookup. ``prefix`` (the
    first few characters of the key) is safe to display so users can tell their keys apart.
    Revocation is soft: ``revoked_at`` is set rather than deleting the row, preserving an
    audit trail and the ``last_used_at`` history.
    """

    __tablename__ = "api_key"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Owner of the key — deleting the user cascades its keys away.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Human-readable label chosen by the user (e.g. "CI pipeline").
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Hash of the API key — looked up on every authenticated request, hence indexed.
    # The plaintext key is NEVER stored.
    key_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    # First characters of the key (e.g. 8 chars) — displayed in the UI to identify the key.
    prefix: Mapped[str] = mapped_column(Text, nullable=False)
    # Per-collection capability scope (keys-only authz model). Shape:
    #   {"entries": [{"collection_id": "*"|"<uuid>", "role": "read"|"write"|"admin"|"custom",
    #                 "capabilities": ["documents.read", ...]}]}
    # NULL = FULL access (the static root env key, or a legacy key created before scoping existed)
    # — kept full for backward compatibility. A non-NULL scope restricts the key per collection.
    permissions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Updated opportunistically on use — NULL until the key is first used.
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Soft-revoke marker — NULL means the key is active; a timestamp means revoked.
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationship
    user: Mapped[AppUserModel] = relationship(back_populates="api_keys")

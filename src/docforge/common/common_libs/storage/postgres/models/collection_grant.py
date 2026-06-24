# ====== Code Summary ======
# SQLAlchemy ORM model for a per-collection authorization grant (GitHub-collaborator model).
# One row = one user holding one role (read | write | admin) on one collection. A unique
# (user_id, collection_id) constraint enforces a single grant per user per collection.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# ====== Local Project Imports ======
from .base import Base

# Cross-model relationship uses a string class name resolved by the SQLAlchemy registry;
# the import is type-checking only to avoid a runtime circular import.
if TYPE_CHECKING:
    from .app_user import AppUserModel


class CollectionGrantModel(Base):
    """
    Per-collection authorization grant (GitHub-collaborator model).

    Each row grants one user a single role on one collection. The role (``read`` |
    ``write`` | ``admin``, values from ``GrantRole``) governs what the user may do
    within that collection. ``granted_by`` records the granting user for audit; it is
    nullable and set to NULL if that granter is later deleted, so the grant survives.
    A unique (user_id, collection_id) pair guarantees at most one grant per user per
    collection — re-granting updates the existing row (see the repository's ``upsert``).
    """

    __tablename__ = "collection_grant"
    __table_args__ = (
        # At most one grant per (user, collection). Backs the repository upsert.
        UniqueConstraint(
            "user_id", "collection_id", name="uq_collection_grant_user_collection"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Grantee — deleting the user cascades the grant away. Indexed to list a user's
    # collections cheaply.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Target collection — deleting the collection cascades its grants away. Indexed to
    # list a collection's collaborators cheaply.
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("collection.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Per-collection role: "read" | "write" | "admin" (values from GrantRole). Plain
    # VARCHAR column; the StrEnum is the source of truth for legal values in Python.
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # Auditing — who granted this. SET NULL on granter deletion so the grant outlives it.
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship to the grantee. ``foreign_keys`` is pinned to user_id because this
    # table has two FKs into app_user (user_id and granted_by) — without it SQLAlchemy
    # cannot pick which one backs the relationship.
    user: Mapped[AppUserModel] = relationship(
        back_populates="grants", foreign_keys=[user_id]
    )

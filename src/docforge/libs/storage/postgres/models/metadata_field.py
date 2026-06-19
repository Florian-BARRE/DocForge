# ====== Code Summary ======
# SQLAlchemy ORM model for the per-collection metadata field definition.
# Each field carries the three orthogonal search capabilities
# (filterable / lexical / semantic) plus RRF fusion weights.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from sqlalchemy import ARRAY, Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# ====== Local Project Imports ======
from .base import Base

# Cross-model relationship uses a string class name resolved by the SQLAlchemy registry;
# the import is type-checking only to avoid a runtime circular import.
if TYPE_CHECKING:
    from .collection import CollectionModel


class MetadataFieldModel(Base):
    """
    Per-collection metadata field definition.

    Each field carries three orthogonal search capabilities (filterable/lexical/semantic)
    plus RRF fusion weights.  System fields (filename, language, page, …) have is_system=True.
    """

    __tablename__ = "metadata_field"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collection.id", ondelete="CASCADE"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(255), nullable=False)
    field_type: Mapped[str] = mapped_column(String(30), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    filterable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lexical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    semantic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enum_values: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationship
    collection: Mapped[CollectionModel] = relationship(back_populates="metadata_fields")

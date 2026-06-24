# ====== Code Summary ======
# SQLAlchemy ORM model for the Collection table — the central contract object.
# A Collection defines supported formats, metadata schema, ingestion pipeline,
# locality policy, and retrieval defaults.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

# ====== Third-Party Library Imports ======
from sqlalchemy import ARRAY, JSON, Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# ====== Local Project Imports ======
from .base import Base

# Cross-model relationships use string class names resolved by the SQLAlchemy registry;
# imports are type-checking only to avoid runtime circular imports.
if TYPE_CHECKING:
    from .document import DocumentModel
    from .metadata_field import MetadataFieldModel


class CollectionModel(Base):
    """
    Persisted representation of a Collection (the central contract object).

    A Collection defines: supported formats, metadata schema, ingestion pipeline,
    locality policy, and retrieval defaults.  One embedding_model per collection —
    changing it requires a new pipeline_version and a full reindex.
    """

    __tablename__ = "collection"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    supported_formats: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    max_file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    unknown_field_policy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="reject"
    )
    locality_policy: Mapped[str] = mapped_column(String(30), nullable=False)
    allowed_providers: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    pipeline: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v1")
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    default_search: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # Set when a config change invalidates the vector space (e.g. embedding_model change) —
    # existing vectors are stale until a reindex runs.
    needs_reindex: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Resource-admission limits (Brique D) — kept as columns (NOT in the pipeline JSON blob) so they
    # never perturb reindex semantics. NULL = no per-collection cap (fall back to global / unlimited).
    max_in_flight: Mapped[int | None] = mapped_column(Integer, nullable=True)
    budget_cap_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships — referenced by string class name, resolved by the SQLAlchemy
    # registry once all model modules are imported in the package __init__.
    metadata_fields: Mapped[list[MetadataFieldModel]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )
    documents: Mapped[list[DocumentModel]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )

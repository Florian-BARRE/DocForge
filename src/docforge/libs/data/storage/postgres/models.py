# ====== Code Summary ======
# SQLAlchemy 2.0 ORM models for the DocForge Postgres schema.
# These are the source of truth for all document catalogue data.
# Qdrant is a derived, regenerable index — never the source of truth.
#
# SIZE EXCEPTION: This file is ~268 lines and slightly exceeds the ~250-line guideline.
# Splitting ORM declarative models across multiple files is anti-idiomatic in SQLAlchemy:
# all models must share the same `DeclarativeBase` instance, cross-table relationships
# (e.g. CollectionModel ↔ DocumentModel ↔ BlockModel) require mutual forward references,
# and tools like Alembic's autogenerate expect to discover all models in a single import.
# The 9 table classes here are tightly coupled by FK constraints and cannot be
# independently understood — keeping them co-located is the correct engineering trade-off.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from sqlalchemy import (
    ARRAY,
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative base for all DocForge ORM models."""
    pass


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    metadata_fields: Mapped[list["MetadataFieldModel"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )
    documents: Mapped[list["DocumentModel"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )


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
    collection: Mapped["CollectionModel"] = relationship(back_populates="metadata_fields")


class DocumentModel(Base):
    """
    Catalogue record for an ingested document.

    source_hash (sha256) is the content-address of the original file.
    Deduplication: same source_hash + pipeline_version → no-op (returned as 200).
    """

    __tablename__ = "document"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collection.id", ondelete="CASCADE"), nullable=False
    )
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    user_meta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    implicit_meta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False)
    # status: pending | processing | done | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    collection: Mapped["CollectionModel"] = relationship(back_populates="documents")
    blocks: Mapped[list["BlockModel"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["JobModel"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class BlockModel(Base):
    """
    Persisted IR block — the granular unit of the document tree stored in Postgres.

    type_data holds type-specific payload:
      - TABLE blocks: cells, n_rows, n_cols, has_header
      - FIGURE blocks: kind, crop_key, relevance, ocr_text, description, data_table
    """

    __tablename__ = "block"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    type_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Relationship
    document: Mapped["DocumentModel"] = relationship(back_populates="blocks")


class StageRunModel(Base):
    """
    Node cache index (P2 stage engine).

    Records the fingerprint and output_ref of every completed stage node.
    Cache hit = same (document_id, node_id, fingerprint) already present with status='done'.
    """

    __tablename__ = "stage_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    output_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderCallModel(Base):
    """
    Provider-call cache (P2 stage engine).

    Deduplicates expensive OCR/VLM/embed calls across documents.
    Key: blake3(capability, provider_id, provider_version, params, content_hash).
    """

    __tablename__ = "provider_call"

    call_fp: Mapped[str] = mapped_column(String(128), primary_key=True)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_version: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    result_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cost: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class JobModel(Base):
    """
    Async ingestion job record.

    Created at admission time; updated by the pipeline runner (BackgroundTasks in P1,
    arq workers in P2+).
    """

    __tablename__ = "job"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    # status: pending | running | done | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_spent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship
    document: Mapped["DocumentModel"] = relationship(back_populates="jobs")


class ConfigVersionModel(Base):
    """
    A historical snapshot of a collection's configuration.

    Written on every config change (update / import / reset) so the config history can be
    listed and a previous version restored (spec — config history / rollback).
    """

    __tablename__ = "config_version"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collection.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

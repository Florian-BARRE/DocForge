# ====== Code Summary ======
# The `document` table — the catalogue record of an ingested document. Identity (content-address),
# origin facts (filename, format, mime, size, pages, language), the acquisition ROUTING signal
# (source_kind: digital-born vs scanned), the near-dup signature, the ingestion status, and the
# pipeline version it ran under. Metadata VALUES live relationally in `document_metadata`, not here.

# ====== Standard Library Imports ======
import uuid
from enum import StrEnum

# ====== Third-Party Library Imports ======
from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, TimestampedMixin, UUIDPrimaryKey, value_enum


class SourceKind(StrEnum):
    """How the document's content is carried — the S0 routing decision."""

    DIGITAL_BORN = "digital_born"  # extractable text (native PDF/office)
    SCANNED = "scanned"  # image-only pages → OCR/VLM
    MIXED = "mixed"  # some pages each


class DocumentStatus(StrEnum):
    """Lifecycle of a document's ingestion."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    # Terminal state for a document whose ingestion was explicitly cancelled (distinct from a genuine
    # FAILED so it reads as "stopped on purpose, re-ingestable" in the UI). "cancelled" (9 chars) fits
    # the existing VARCHAR(10) status column ("processing" is longer), so this adds no column-width DDL.
    CANCELLED = "cancelled"


class Document(Base, UUIDPrimaryKey, TimestampedMixin):
    """Catalogue record for one ingested document."""

    __tablename__ = "document"
    # Read-path indexes for the server-side document grid (filter/sort at 100k docs). Created by
    # migration c3e9a1f7d2b4; declared here so ``--autogenerate`` reconciles them instead of dropping
    # them. The metadata-side functional index ``ix_docmeta_field_value_text`` and GIN index
    # ``ix_docmeta_value_gin`` are intentionally left migration-only (expression/GIN indexes compare
    # unreliably under autogenerate) — see ``DocumentMetadata``.
    __table_args__ = (
        UniqueConstraint("collection_id", "source_hash", "pipeline_version"),
        Index("ix_document_collection_created_at", "collection_id", text("created_at DESC")),
        Index("ix_document_collection_status", "collection_id", "status"),
        Index("ix_document_collection_filename", "collection_id", "filename"),
        Index("ix_document_collection_enabled", "collection_id", "enabled"),
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collection.id", ondelete="CASCADE"), nullable=False
    )
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # The canonical PDF view produced by conversion (None until converted, or when the original
    # already is the PDF). The ORIGINAL bytes are blob(source_hash) — content-addressed by design.
    pdf_blob_hash: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("blob.content_hash", ondelete="SET NULL"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_kind: Mapped[SourceKind] = mapped_column(value_enum(SourceKind), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    simhash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # near-dup signature
    status: Mapped[DocumentStatus] = mapped_column(
        value_enum(DocumentStatus), nullable=False, default=DocumentStatus.PENDING
    )
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False)
    # The user's document-level searchability toggle — a plain on/off (documents have no role).
    # Disabling hides every chunk of the document from retrieval regardless of chunk-level state.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


__all__ = ["Document", "DocumentStatus", "SourceKind"]

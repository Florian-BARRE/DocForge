# ====== Code Summary ======
# The `artifact_cache` table — a per-collection, content-addressed cache of stage outputs for the
# ingestion pipeline. The cached BYTES live in S3 (registered in the `blob` table under their
# content_hash as BlobKind.STAGE_ARTIFACT); THIS table is only the pointer + GC bookkeeping. A
# worker-side cache hook INSERTs one row per cached stage output, keyed by a sha256 Merkle
# `cache_key` (the collection_id is already folded into that key by the pipeline; the column here is
# kept for attribution and GC scoping). Lookup is by exact `cache_key`, so the natural key IS the
# primary key — no surrogate. The row holds NO hard foreign keys: it must never block (nor be
# required to survive) a document or collection delete — GC reclaims orphaned rows and their S3
# bytes on its own schedule.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from enum import StrEnum

# ====== Third-Party Library Imports ======
from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, CreatedAtMixin, value_enum


class ArtifactType(StrEnum):
    """Which stage artifact a cached row holds. Starts with the parse IR; more added later."""

    PARSE_IR = "parse_ir"  # the canonical DocumentIR produced by the PARSE stage


class ArtifactCache(Base, CreatedAtMixin):
    """A pointer + GC-bookkeeping row for one cached stage output whose bytes live in S3."""

    __tablename__ = "artifact_cache"
    # GC read-path indexes. None is redundant with the PK (which serves only exact-key lookup).
    __table_args__ = (
        # LRU / TTL sweep + per-collection size cap: scope by collection, order/prune by recency.
        Index("ix_artifact_cache_collection_last_hit", "collection_id", "last_hit_at"),
        # Ref-count orphan sweep: before deleting an S3 object, is any cache_key still pointing at it?
        Index("ix_artifact_cache_content_hash", "content_hash"),
        # On-document-delete cleanup: drop every cache row attributed to a deleted document.
        Index("ix_artifact_cache_document_id", "document_id"),
    )

    # The sha256 hex Merkle key. PRIMARY KEY: lookup is by exact key, so the natural key IS the
    # identity — no surrogate. The collection_id is already folded into this value upstream.
    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)

    # The sha256 of the cached artifact bytes = the S3 key / `blob.content_hash` this row points at.
    # Many cache_keys may point at the same content_hash (dedup), hence its own non-unique index.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # The human-debuggable composite (family/kind/version) the cache_key was derived from.
    stage_key: Mapped[str] = mapped_column(Text, nullable=False)

    # Which stage artifact this is. value_enum → VARCHAR (no CHECK), so new members are code-only.
    artifact_type: Mapped[ArtifactType] = mapped_column(value_enum(ArtifactType), nullable=False)

    # The CACHE_VERSION+EPOCH string folded into the key — kept for debug/audit.
    engine_version: Mapped[str] = mapped_column(String(128), nullable=False)

    # Attribution ids stored RAW with NO foreign key: the cache row must never block a document or
    # collection delete, and GC (which sweeps by these columns) owns lifecycle cleanup. document_id
    # is nullable (collection-level artifacts have no single document); collection_id is always set.
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    collection_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    # Size of the cached bytes — feeds the per-collection cap accounting.
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Recency + popularity, maintained on every cache HIT (last_hit_at NULL until first hit).
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


__all__ = ["ArtifactCache", "ArtifactType"]

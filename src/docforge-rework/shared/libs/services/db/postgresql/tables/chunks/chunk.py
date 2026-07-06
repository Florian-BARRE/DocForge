# ====== Code Summary ======
# The `chunk` table — the retrieval unit. Its `id` IS the Qdrant point id (a deterministic UUID v5),
# so a search hit maps back here by primary key. It stores the ENRICHED form only — `text` is what
# gets embedded (breadcrumb + assembled block content, with figures contributing their VLM/OCR text
# and the LLM contextual prefix). The RAW chunk is NOT stored: it is recomputed from `chunk_block` →
# `block.text`, so nothing is duplicated. Hierarchical chunking uses `parent_id` (self-reference).

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, TimestampedMixin


class Chunk(Base, TimestampedMixin):
    """A retrieval unit — its id doubles as the Qdrant point id; it stores the enriched text."""

    __tablename__ = "chunk"
    __table_args__ = (Index("ix_chunk_document_config", "document_id", "config_hash"),)

    # App-set UUID v5 (document + block ids + config) — stable, so re-ingest overwrites the same
    # Qdrant point. No server default: the chunker always supplies it.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy: Mapped[str] = mapped_column(Text, nullable=False)
    # Deferred self-FK: the hierarchy check runs at COMMIT, so bulk inserts never depend on the
    # parent/child ordering of the rows (large documents split across several INSERT statements).
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("chunk.id", ondelete="SET NULL", deferrable=True, initially="DEFERRED"),
        nullable=True,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)  # the enriched, embedded text
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    simhash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # near-dup signature
    is_indexed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


__all__ = ["Chunk"]

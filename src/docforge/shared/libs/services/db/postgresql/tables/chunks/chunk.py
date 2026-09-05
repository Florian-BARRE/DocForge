# ====== Code Summary ======
# The `chunk` table — the retrieval unit. Its `id` IS the Qdrant point id (a deterministic UUID v5
# minted by the worker's RunTranslator from (document_id, chunk_index)), so a search hit maps back
# here by primary key AND a re-ingest of the same chunk upserts the SAME point (idempotent). It
# stores the ENRICHED (embedded) form only — `text` is the LLM contextual prefix over the assembled
# block content, with figures contributing their VLM/OCR text. The RAW, pre-enrichment chunk text is
# NOT stored and NOT reliably recoverable: stripping the prefix yields the enriched assembly (already
# folding in figure OCR/VLM text), and re-joining `block.text` via `chunk_block` loses the figure
# contributions and the chunker's exact assembly. Hierarchical chunking uses `parent_id`.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, TimestampedMixin


class Chunk(Base, TimestampedMixin):
    """A retrieval unit — its id doubles as the Qdrant point id; it stores the enriched text."""

    __tablename__ = "chunk"
    __table_args__ = (Index("ix_chunk_document_config", "document_id", "config_hash"),)

    # Deterministic UUID v5 keyed on (document_id, chunk_index) — stable across runs, so re-ingest
    # overwrites the same Qdrant point. No server default: the RunTranslator always supplies it.
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
    # Section ancestry TEXTS, top-down (e.g. ["Chapter 2", "Results"]) — computed at chunking time
    # and carried here so a search hit can self-cite the clause/section it came from. NULL on rows
    # that predate this column; the read path coalesces NULL to an empty list.
    heading_path: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    simhash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # near-dup signature
    is_indexed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # The pipeline's structural classification — a ChunkRole value ("body" / "header_footer" /
    # "toc" / "boilerplate"). Stored as a plain VARCHAR (like block.block_type) so the Python
    # StrEnum owns the value set and new roles need no PG enum ALTER. Drives the default enabled
    # state via role_default_enabled(); existing rows backfill to "body".
    role: Mapped[str] = mapped_column(String(32), nullable=False, server_default="body")
    # The user's per-chunk manual override of searchability. NULL = no override → defer to
    # role_default_enabled(role); True/False = an explicit user choice that wins over the role
    # default. Effective enabled state = enabled_override ?? role_default_enabled(role).
    enabled_override: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


__all__ = ["Chunk"]

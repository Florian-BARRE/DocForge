# ====== Code Summary ======
# The `chunk_block` table — the M:N relation between a chunk and the IR blocks it is assembled from,
# with the assembly order (`position`). It answers both directions: which blocks make up a chunk
# (to recompute the raw chunk), and in which chunks a given block appears. Replaces an opaque
# block_ids array with a real, queryable relation.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base


class ChunkBlock(Base):
    """A chunk ↔ block membership, ordered — the composition of a chunk."""

    __tablename__ = "chunk_block"
    # The composite PK only covers chunk_id as leading column; block-side lookups (which chunks use
    # this block? CASCADE on block delete) need their own index.
    __table_args__ = (Index("ix_chunk_block_block_id", "block_id"),)

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("chunk.id", ondelete="CASCADE"), primary_key=True
    )
    block_id: Mapped[str] = mapped_column(
        String(256), ForeignKey("block.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # assembly order within the chunk


__all__ = ["ChunkBlock"]

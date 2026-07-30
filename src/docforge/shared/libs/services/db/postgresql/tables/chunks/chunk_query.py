# ====== Code Summary ======
# The `chunk_query` table — doc2query synthetic questions a chunk answers (one row each). They are
# indexed on the sparse side to lift recall: a user query phrased as a question matches these even
# when it shares few words with the chunk body.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, CreatedAtMixin, UUIDPrimaryKey


class ChunkQuery(Base, UUIDPrimaryKey, CreatedAtMixin):
    """A synthetic question a chunk answers (doc2query)."""

    __tablename__ = "chunk_query"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("chunk.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)


__all__ = ["ChunkQuery"]

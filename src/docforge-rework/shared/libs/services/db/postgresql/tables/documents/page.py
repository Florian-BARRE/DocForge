# ====== Code Summary ======
# The `page` table — per-page facts of a document. Routing (OCR vs direct extraction), language and
# the rendered image are decided PER PAGE, not per document: one page may be scanned while the next
# is digital-born. The page image render lives in S3, referenced here by its blob content hash.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, UUIDPrimaryKey


class Page(Base, UUIDPrimaryKey):
    """Per-page facts: routing, language and the page render."""

    __tablename__ = "page"
    __table_args__ = (UniqueConstraint("document_id", "page_number"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[float | None] = mapped_column(Float, nullable=True)
    height: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_scanned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    render_blob_hash: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("blob.content_hash", ondelete="SET NULL"), nullable=True, index=True
    )


__all__ = ["Page"]

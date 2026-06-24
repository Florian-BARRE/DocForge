# ====== Code Summary ======
# SQLAlchemy ORM model for the node cache index (P2 stage engine).
# Records the fingerprint and output_ref of every completed stage node so that
# repeated runs can be served from cache.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime

# ====== Third-Party Library Imports ======
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from .base import Base


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

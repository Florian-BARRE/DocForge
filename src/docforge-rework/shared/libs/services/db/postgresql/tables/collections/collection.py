# ====== Code Summary ======
# The `collection` table — a collection's ingestion contract, kept lean: its name, the document
# formats it accepts, the per-file size cap, the reindex flag, and its two config blobs (the
# pipeline config and the search config). Everything else the audit needs (embedding model,
# versioning) is derived from, or lives inside, the pipeline config — not duplicated as columns.

# ====== Third-Party Library Imports ======
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

# ====== Local Project Imports ======
from ..base import Base, TimestampedMixin, UUIDPrimaryKey


class Collection(Base, UUIDPrimaryKey, TimestampedMixin):
    """A collection and its ingestion contract."""

    __tablename__ = "collection"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    supported_formats: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    max_file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    needs_reindex: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pipeline: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # pipeline config blob
    search: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)    # search config blob
    # created_at + updated_at come from TimestampedMixin


__all__ = ["Collection"]

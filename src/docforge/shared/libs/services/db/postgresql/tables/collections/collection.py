# ====== Code Summary ======
# The `collection` table — a collection's contract, kept lean: its name, the document formats it
# accepts, the per-file size cap, the reindex flag, and its two graph blobs (the ingestion pipeline
# graph and the search pipeline graph). Everything else the audit needs (embedding model,
# versioning) is derived from, or lives inside, the pipeline config — not duplicated as columns.

# ====== Third-Party Library Imports ======
from sqlalchemy import Boolean, Float, Integer, String
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
    # Per-collection override of the whole-ingest-job wall-clock budget, in seconds. NULL = fall back
    # to the worker's global WORKER_JOB_TIMEOUT_SECONDS; a set value caps this collection's jobs.
    job_timeout_seconds: Mapped[float | None] = mapped_column(
        Float, nullable=True, server_default=None
    )
    needs_reindex: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pipeline: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )  # ingestion graph blob
    # A SEARCH GRAPH BLOB (a serialized search-pipeline topology); {} = use the stock default.
    search: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # created_at + updated_at come from TimestampedMixin


__all__ = ["Collection"]

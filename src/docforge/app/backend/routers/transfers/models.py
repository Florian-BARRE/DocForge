# ====== Code Summary ======
# Pydantic request/response models for the collection transfer (export/import) router: the 202
# acceptance envelope returned when a transfer is enqueued, and the full poll model the status
# endpoint serves from a `collection_transfer` row.

# ====== Standard Library Imports ======
from __future__ import annotations

from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class TransferAccepted(BaseModel):
    """
    The 202 envelope returned the instant a transfer is created and enqueued.

    Attributes:
        transfer_id (str): The tracking row's id — poll GET /transfers/{id} with it.
        kind (str): The transfer direction ("export" or "import").
        status (str): The transfer's status at acceptance (always "pending").
    """

    transfer_id: str = Field(..., description="The tracking row's id; poll it for progress.")
    kind: str = Field(..., description="Transfer direction: 'export' or 'import'.")
    status: str = Field(..., description="Lifecycle status at acceptance (pending).")


class TransferStatus(BaseModel):
    """
    The full poll model of a collection transfer — its live status and (when done) its artifact.

    Attributes:
        transfer_id (str): The tracking row's id.
        kind (str): "export" or "import".
        status (str): pending / running / done / failed.
        progress (int): Coarse 0-100 percentage.
        stage (str | None): The current engine stage label, when running.
        counts (dict | None): Per-table counts snapshot ({"documents": n, "chunks": m, ...}).
        error (str | None): The failure message, verbatim, when failed.
        collection_id (str | None): Export → the source collection; import → the NEW collection once
            done (None while an import is still in flight).
        collection_name (str | None): The source (export) or produced (import) collection name.
        size_bytes (int | None): The produced export bundle's size (done export only).
        format_version (int | None): The bundle format version (done export only).
        dense_dim (int | None): The captured dense vector size (done export only).
        expires_at (datetime | None): When a produced export bundle may be garbage-collected.
        started_at (datetime | None): When the worker claimed the transfer.
        finished_at (datetime | None): When the transfer reached a terminal state.
        created_at (datetime): When the tracking row was created.
        updated_at (datetime): When the tracking row was last touched.
    """

    transfer_id: str = Field(..., description="The tracking row's id.")
    kind: str = Field(..., description="Transfer direction: 'export' or 'import'.")
    status: str = Field(..., description="Lifecycle status: pending / running / done / failed.")
    progress: int = Field(..., description="Coarse completion percentage (0-100).")
    stage: str | None = Field(None, description="Current engine stage label, when running.")
    counts: dict[str, Any] | None = Field(None, description="Per-table counts snapshot.")
    error: str | None = Field(None, description="Failure message (verbatim) when failed.")
    collection_id: str | None = Field(
        None, description="Export: source collection. Import: the new collection once done."
    )
    collection_name: str | None = Field(None, description="Source or produced collection name.")
    size_bytes: int | None = Field(None, description="Produced bundle size in bytes (done export).")
    format_version: int | None = Field(None, description="Bundle format version (done export).")
    dense_dim: int | None = Field(None, description="Captured dense vector size (done export).")
    expires_at: datetime | None = Field(None, description="When a produced bundle may be GC'd.")
    started_at: datetime | None = Field(None, description="When the worker claimed the transfer.")
    finished_at: datetime | None = Field(
        None, description="When the transfer reached a terminal state."
    )
    created_at: datetime = Field(..., description="When the tracking row was created.")
    updated_at: datetime = Field(..., description="When the tracking row was last touched.")

    @classmethod
    def from_row(cls, row: Any) -> TransferStatus:
        """
        Map a `collection_transfer` ORM row onto the poll model.

        Args:
            row (Any): The CollectionTransfer row the worker maintains.

        Returns:
            TransferStatus: The serialized status surface.
        """
        # 1. StrEnum columns (kind/status) serialize to their string value; ids to str.
        return cls(
            transfer_id=str(row.id),
            kind=str(row.kind),
            status=str(row.status),
            progress=row.progress,
            stage=row.stage,
            counts=row.counts,
            error=row.error,
            collection_id=str(row.collection_id) if row.collection_id is not None else None,
            collection_name=row.collection_name,
            size_bytes=row.size_bytes,
            format_version=row.format_version,
            dense_dim=row.dense_dim,
            expires_at=row.expires_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


__all__ = ["TransferAccepted", "TransferStatus"]

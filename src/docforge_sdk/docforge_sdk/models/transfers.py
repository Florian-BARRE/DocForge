# ====== Code Summary ======
# Response models for the collection transfer (export/import) endpoints, mirrored field-for-field
# from the DocForge backend router models (transfers/models.py): the 202 acceptance envelope and the
# full poll model a transfer's status is served from.

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class TransferAccepted(BaseModel):
    """
    The 202 envelope returned the instant a transfer is created and enqueued.

    Attributes:
        transfer_id (str): The tracking row's id; poll it for progress.
        kind (str): Transfer direction: "export" or "import".
        status (str): Lifecycle status at acceptance (pending).
    """

    transfer_id: str = Field(description="The tracking row's id; poll it for progress.")
    kind: str = Field(description="Transfer direction: 'export' or 'import'.")
    status: str = Field(description="Lifecycle status at acceptance (pending).")


class TransferStatus(BaseModel):
    """
    The full poll model of a collection transfer — its live status and (when done) its artifact.

    Attributes:
        transfer_id (str): The tracking row's id.
        kind (str): "export" or "import".
        status (str): pending / running / done / failed.
        progress (int): Coarse 0-100 percentage.
        stage (str | None): The current engine stage label, when running.
        counts (dict[str, Any] | None): Per-table counts snapshot ({"documents": n, "chunks": m, ...}).
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

    transfer_id: str = Field(description="The tracking row's id.")
    kind: str = Field(description="Transfer direction: 'export' or 'import'.")
    status: str = Field(description="Lifecycle status: pending / running / done / failed.")
    progress: int = Field(description="Coarse completion percentage (0-100).")
    stage: str | None = Field(default=None, description="Current engine stage label, when running.")
    counts: dict[str, Any] | None = Field(default=None, description="Per-table counts snapshot.")
    error: str | None = Field(default=None, description="Failure message (verbatim) when failed.")
    collection_id: str | None = Field(
        default=None, description="Export: source collection. Import: the new collection once done."
    )
    collection_name: str | None = Field(
        default=None, description="Source or produced collection name."
    )
    size_bytes: int | None = Field(
        default=None, description="Produced bundle size in bytes (done export)."
    )
    format_version: int | None = Field(
        default=None, description="Bundle format version (done export)."
    )
    dense_dim: int | None = Field(
        default=None, description="Captured dense vector size (done export)."
    )
    expires_at: datetime | None = Field(
        default=None, description="When a produced bundle may be GC'd."
    )
    started_at: datetime | None = Field(
        default=None, description="When the worker claimed the transfer."
    )
    finished_at: datetime | None = Field(
        default=None, description="When the transfer reached a terminal state."
    )
    created_at: datetime = Field(description="When the tracking row was created.")
    updated_at: datetime = Field(description="When the tracking row was last touched.")


__all__ = ["TransferAccepted", "TransferStatus"]

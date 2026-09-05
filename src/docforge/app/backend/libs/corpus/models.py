# ====== Code Summary ======
# The response + selector models for the document grid. A grid ROW is the explorer's DocumentListItem
# plus a compact ``{field_name: value}`` map of the collection's document-metadata (bulk-loaded per
# page, never N+1). The DocumentSelector is the ONE shared target model every bulk op takes: either
# an explicit id list XOR a filter (+ a few deselected ids) — this is what lets "select all 100k
# matching, deselect 3, act on the rest" work without ever enumerating ids client-side. Bulk-op
# responses report ``matched`` (the resolved target count) distinctly from what actually happened.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field, model_validator

# ====== Local Project Imports ======
from ...libs.reingest import ReingestJobHandle
from ...routers.explorer.models import DocumentListItem
from .filters import DocumentFilter


class DocumentGridRow(DocumentListItem):
    """One grid row — the base catalogue fields plus a compact document-metadata value map."""

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Document-level metadata as {field_name: value} (only the schema's fields).",
    )


class DocumentQueryResponse(BaseModel):
    """A page of grid rows plus the total match count and the pagination echo."""

    total: int = Field(description="Total documents matching the filter (drives the pager).")
    limit: int = Field(description="The applied page size (after the server ceiling clamp).")
    offset: int = Field(description="The applied offset.")
    rows: list[DocumentGridRow] = Field(description="The page of rows, in the requested order.")


class DocumentSelector(BaseModel):
    """
    The shared bulk-op target: an explicit id set XOR a filter (minus a few deselected ids).

    Exactly one mode is allowed. In id mode, ``document_ids`` is the literal target set (non-empty).
    In filter mode, ``filter`` selects everything matching (an empty filter = the whole collection)
    and ``exclude_ids`` removes a deselected few — the "select-all-minus-N" the UI needs at 100k
    scale. ``exclude_ids`` is only meaningful in filter mode; supplying it in id mode is a 422.
    """

    model_config = ConfigDict(extra="forbid")

    document_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="Explicit target ids (id mode). Mutually exclusive with ``filter``.",
    )
    filter: DocumentFilter | None = Field(
        default=None,
        description="Everything matching (filter mode). An empty filter means the whole collection.",
    )
    exclude_ids: list[uuid.UUID] = Field(
        default_factory=list,
        description="Ids to deselect from the filter result (filter mode only).",
    )

    @model_validator(mode="after")
    def _validate_mode(self) -> "DocumentSelector":
        """Enforce the id-XOR-filter contract and the mode-specific field rules."""
        # 1. Exactly one mode — never both, never neither.
        if (self.document_ids is None) == (self.filter is None):
            raise ValueError("Provide exactly one of 'document_ids' or 'filter'.")
        # 2. Id mode: a non-empty explicit set, and exclude_ids makes no sense.
        if self.document_ids is not None:
            if not self.document_ids:
                raise ValueError("'document_ids' must be a non-empty list.")
            if self.exclude_ids:
                raise ValueError("'exclude_ids' is only valid with 'filter'.")
        return self


class BulkDeleteResponse(BaseModel):
    """The outcome of a bulk delete — how many were targeted vs actually removed (+ the cap signal)."""

    collection_id: str = Field(description="The target collection's UUID.")
    matched: int = Field(
        description="Documents this call targeted (<= the per-call selection cap)."
    )
    deleted: int = Field(description="Documents actually deleted everywhere (PG + Qdrant + S3).")
    capped: bool = Field(
        default=False,
        description="True when the match exceeded the per-call selection cap — more remain; re-run "
        "the same selector to delete them (delete is convergent).",
    )
    max_selection: int = Field(
        default=0, description="The per-call selection cap that was applied."
    )


class BulkEnabledResponse(BaseModel):
    """The outcome of a bulk enable/disable — targeted vs actually changed, plus the reindex note."""

    collection_id: str = Field(description="The target collection's UUID.")
    enabled: bool = Field(description="The state applied to every target.")
    matched: int = Field(description="Documents the selector resolved to.")
    updated: int = Field(
        description="Documents whose state actually changed (already-in-state skip)."
    )
    reindex_implied: bool = Field(
        description="Always false — a document toggle is a Postgres flag, never a re-index."
    )


class BulkReingestResponse(BaseModel):
    """The accepted bulk re-run — targeted vs enqueued, whether the fan-out hit the cap, and handles."""

    collection_id: str = Field(description="The target collection's UUID.")
    matched: int = Field(description="Documents the selector resolved to.")
    enqueued: int = Field(description="Jobs actually enqueued (<= the fan-out ceiling).")
    capped: bool = Field(
        description="True when the match count exceeded the per-call fan-out ceiling."
    )
    max_fanout: int = Field(description="The per-call fan-out ceiling that was applied.")
    jobs: list[ReingestJobHandle] = Field(
        description="One handle per enqueued run (poll each job)."
    )


__all__ = [
    "DocumentGridRow",
    "DocumentQueryResponse",
    "DocumentSelector",
    "BulkDeleteResponse",
    "BulkEnabledResponse",
    "BulkReingestResponse",
]

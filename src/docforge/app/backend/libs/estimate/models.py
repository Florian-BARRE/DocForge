# ====== Code Summary ======
# The request model of the collection cost-estimate endpoint. The response is the pure
# ``CostEstimate`` (from the estimator package) reused verbatim — an estimate is exactly what the
# endpoint returns, so there is no separate response wrapper to keep in sync. The request selects
# WHICH documents the estimate covers: a whole-collection ``scope`` (pending / all), an explicit
# ``document_ids`` subset (selected rows / freshly uploaded files), or a corpus ``filter`` reusing
# the document-grid's exact filter shape (estimate over a filtered subset).

# ====== Standard Library Imports ======
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field, model_validator

# ====== Internal Project Imports ======
from ...libs.corpus import DocumentFilter


class CollectionEstimateRequest(BaseModel):
    """
    Body of ``POST /collections/{id}/estimate`` — which documents to project the cost over.

    Three mutually-refining selectors, in precedence order: an explicit ``document_ids`` subset, a
    corpus ``filter`` subset (the SAME shape the document grid uses), or — when neither is given —
    the whole-collection ``scope``. ``document_ids`` and ``filter`` are mutually exclusive; when
    either is provided ``scope`` is ignored (the subset is explicit).

    Attributes:
        scope (Literal): Whole-collection selector when no subset is given — ``pending`` (uploaded
            but not yet ingested, the default preview target) or ``all`` (every document).
        document_ids (list[str] | None): Estimate over exactly these documents (must exist and belong
            to the collection). Mutually exclusive with ``filter``.
        filter (DocumentFilter | None): Estimate over the documents matching this corpus filter (the
            document-grid filter shape). Mutually exclusive with ``document_ids``.
    """

    model_config = ConfigDict(extra="forbid")

    scope: Literal["pending", "all"] = Field(
        default="pending",
        description="Whole-collection selector when no subset is given: 'pending' or 'all'.",
    )
    document_ids: list[str] | None = Field(
        default=None,
        description="Estimate over exactly these document ids (mutually exclusive with 'filter').",
    )
    filter: DocumentFilter | None = Field(
        default=None,
        description="Estimate over the documents matching this corpus filter (mutually exclusive "
        "with 'document_ids').",
    )

    @model_validator(mode="after")
    def _validate_selection(self) -> "CollectionEstimateRequest":
        """Enforce the document_ids-XOR-filter contract and a non-empty explicit id list."""
        # 1. Never both subset selectors at once — the target set would be ambiguous.
        if self.document_ids is not None and self.filter is not None:
            raise ValueError("Provide at most one of 'document_ids' or 'filter'.")
        # 2. An explicit id list, when present, must select something.
        if self.document_ids is not None and not self.document_ids:
            raise ValueError("'document_ids' must be a non-empty list when provided.")
        return self


__all__ = ["CollectionEstimateRequest"]

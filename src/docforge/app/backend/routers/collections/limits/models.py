# ====== Code Summary ======
# Pydantic models for the per-collection resource-limits sub-resource (Brique D): the PUT request
# that replaces the cap, and the response that echoes the cap alongside live usage (in-flight jobs).

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from common_libs.storage.postgres.models import CollectionModel


class CollectionLimitsUpdateRequest(BaseModel):
    """
    Replace a collection's resource-admission limits (PUT semantics — the cap is set).

    Attributes:
        max_in_flight (int | None): Per-collection running+pending cap; null clears it (unlimited).
    """

    # A cap of 0 would freeze the collection (in_flight >= 0 is always true), which is never the
    # intended meaning here — "unlimited" is expressed with null. Reject 0 at the boundary (ge=1)
    # so an operator who means "no limit" cannot accidentally brick ingestion.
    max_in_flight: int | None = Field(
        default=None, ge=1, description="Per-collection running+pending cap (null = unlimited)."
    )


class CollectionLimitsResponse(BaseModel):
    """
    A collection's configured resource limits plus live usage.

    Attributes:
        collection_id (uuid.UUID): The collection these limits apply to.
        max_in_flight (int | None): Configured in-flight cap (null = unlimited).
        in_flight (int): Current running + pending jobs for the collection.
    """

    collection_id: uuid.UUID = Field(..., description="Target collection id.")
    max_in_flight: int | None = Field(None, description="Configured in-flight cap (null = unlimited).")
    in_flight: int = Field(..., description="Current running + pending jobs for the collection.")

    @classmethod
    def from_state(
        cls, collection: "CollectionModel", *, in_flight: int
    ) -> "CollectionLimitsResponse":
        """
        Build the response from a collection row + live usage numbers.

        Args:
            collection (CollectionModel): Source of the configured cap.
            in_flight (int): Current running + pending jobs for the collection.

        Returns:
            CollectionLimitsResponse: Cap + usage.
        """
        # 1. Echo the configured cap alongside the live in-flight count
        return cls(
            collection_id=collection.id,
            max_in_flight=collection.max_in_flight,
            in_flight=in_flight,
        )


# ------------------- Public API ------------------- #
__all__ = ["CollectionLimitsUpdateRequest", "CollectionLimitsResponse"]

# ====== Code Summary ======
# Pydantic models for the per-collection resource-limits sub-resource (Brique D): the PUT request
# that replaces the caps, and the response that echoes the caps alongside live usage (in-flight
# jobs + cumulative spend + remaining budget).

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from libs.storage.postgres.models import CollectionModel


class CollectionLimitsUpdateRequest(BaseModel):
    """
    Replace a collection's resource-admission limits (PUT semantics — both caps are set).

    Attributes:
        max_in_flight (int | None): Per-collection running+pending cap; null clears it (unlimited).
        budget_cap_usd (float | None): Cumulative spend cap in USD; null clears it (unlimited).
    """

    # A cap of 0 would freeze the collection (in_flight >= 0 / spent >= 0 are always true), which is
    # never the intended meaning here — "unlimited" is expressed with null. Reject 0 at the boundary
    # (ge=1 / gt=0) so an operator who means "no limit" cannot accidentally brick ingestion.
    max_in_flight: int | None = Field(
        default=None, ge=1, description="Per-collection running+pending cap (null = unlimited)."
    )
    budget_cap_usd: float | None = Field(
        default=None, gt=0.0, description="Cumulative spend cap in USD (null = unlimited)."
    )


class CollectionLimitsResponse(BaseModel):
    """
    A collection's configured resource limits plus live usage.

    Attributes:
        collection_id (uuid.UUID): The collection these limits apply to.
        max_in_flight (int | None): Configured in-flight cap (null = unlimited).
        budget_cap_usd (float | None): Configured budget cap in USD (null = unlimited).
        in_flight (int): Current running + pending jobs for the collection.
        budget_spent_usd (float): Cumulative USD spent across the collection's jobs.
        budget_remaining_usd (float | None): cap − spent (clamped at 0), or null when uncapped.
    """

    collection_id: uuid.UUID = Field(..., description="Target collection id.")
    max_in_flight: int | None = Field(None, description="Configured in-flight cap (null = unlimited).")
    budget_cap_usd: float | None = Field(None, description="Configured budget cap USD (null = unlimited).")
    in_flight: int = Field(..., description="Current running + pending jobs for the collection.")
    budget_spent_usd: float = Field(..., description="Cumulative USD spent across the collection's jobs.")
    budget_remaining_usd: float | None = Field(
        None, description="Remaining budget (cap − spent, clamped at 0); null when uncapped."
    )

    @classmethod
    def from_state(
        cls, collection: "CollectionModel", *, in_flight: int, budget_spent: float
    ) -> "CollectionLimitsResponse":
        """
        Build the response from a collection row + live usage numbers.

        Args:
            collection (CollectionModel): Source of the configured caps.
            in_flight (int): Current running + pending jobs for the collection.
            budget_spent (float): Cumulative USD spent across the collection's jobs.

        Returns:
            CollectionLimitsResponse: Caps + usage with the derived remaining budget.
        """
        # 1. Remaining budget is only meaningful when a cap is set (clamp negatives to 0)
        remaining = (
            None if collection.budget_cap_usd is None
            else max(0.0, collection.budget_cap_usd - budget_spent)
        )
        return cls(
            collection_id=collection.id,
            max_in_flight=collection.max_in_flight,
            budget_cap_usd=collection.budget_cap_usd,
            in_flight=in_flight,
            budget_spent_usd=round(budget_spent, 6),
            budget_remaining_usd=None if remaining is None else round(remaining, 6),
        )


# ------------------- Public API ------------------- #
__all__ = ["CollectionLimitsUpdateRequest", "CollectionLimitsResponse"]

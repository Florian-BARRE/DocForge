# ====== Code Summary ======
# The request model of the collection cost-estimate endpoint. The response is the pure
# ``CostEstimate`` (from the estimator package) reused verbatim — an estimate is exactly what the
# endpoint returns, so there is no separate response wrapper to keep in sync.

# ====== Standard Library Imports ======
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field


class CollectionEstimateRequest(BaseModel):
    """
    Body of ``POST /collections/{id}/estimate`` — which documents to project the cost over.

    Attributes:
        scope (Literal): Which documents the estimate covers — ``pending`` (uploaded but not yet
            ingested, the default preview target) or ``all`` (every document in the collection).
    """

    model_config = ConfigDict(extra="forbid")

    scope: Literal["pending", "all"] = Field(
        default="pending",
        description="Documents to estimate over: 'pending' (not-yet-ingested) or 'all'.",
    )


__all__ = ["CollectionEstimateRequest"]

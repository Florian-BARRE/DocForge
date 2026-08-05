# ====== Code Summary ======
# The collection-health API contract — the response shape of GET /collections/{id}/health. It is the
# honest, on-demand operational picture of one collection: whether each of its two graphs (ingest,
# search) builds + structurally validates, the per-provider reachability sweep over both, the index
# size + last successful ingest, and the rolled-up verdict / search-operational signal. Pure data
# models — the CollectionHealthService fills them; the router exposes them as its response_model.

# ====== Standard Library Imports ======
from datetime import datetime
from enum import StrEnum
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.reachability import ProviderProbeResult

# The tri-state search-operational signal: a plain bool for the clear cases plus the "degraded"
# middle (query embedder reachable but the index is empty, or a configured reranker is unreachable).
SearchOperational = bool | Literal["degraded"]


class HealthVerdict(StrEnum):
    """The rolled-up operational verdict of a collection."""

    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    DOWN = "down"


class IngestHealth(BaseModel):
    """The ingest graph's health: whether it builds and its provider reachability sweep."""

    buildable: bool = Field(
        description="Whether the stored ingest blob heals, builds and structurally validates."
    )
    build_error: str | None = Field(
        default=None,
        description="The build/validation error when ``buildable`` is false (None otherwise).",
    )
    providers: list[ProviderProbeResult] = Field(
        default_factory=list,
        description="One reachability outcome per provider-hosted ingest action leaf.",
    )


class SearchIndex(BaseModel):
    """The retrieval index facts: how many vectors are stored and when they were last written."""

    vector_count: int = Field(
        description="Number of vector points indexed for the collection (0 when never ingested)."
    )
    last_ingest_at: datetime | None = Field(
        default=None,
        description="Finish time of the most recent successful ingest (None when there is none).",
    )


class SearchHealth(BaseModel):
    """The search graph's health: buildability, provider sweep, index facts and the roll-up."""

    buildable: bool = Field(
        description="Whether the collection's search blob (or the stock default) builds + validates."
    )
    search_operational: SearchOperational = Field(
        description="true / false / 'degraded' — whether a query can actually be served now."
    )
    build_error: str | None = Field(
        default=None,
        description="The search-graph build/validation error when ``buildable`` is false.",
    )
    providers: list[ProviderProbeResult] = Field(
        default_factory=list,
        description="The query embedder outcome plus the reranker's (when one is configured).",
    )
    index: SearchIndex = Field(description="The collection's vector-index size + last ingest time.")


class CollectionHealthResponse(BaseModel):
    """The full on-demand operational health of one collection."""

    collection_id: str = Field(description="The probed collection's id.")
    verdict: HealthVerdict = Field(description="The rolled-up verdict: operational/degraded/down.")
    checked_at: datetime = Field(description="When this probe ran (server time, UTC).")
    ingest: IngestHealth = Field(description="The ingest graph's buildability + provider sweep.")
    search: SearchHealth = Field(description="The search graph's buildability + provider sweep.")


__all__ = [
    "HealthVerdict",
    "SearchOperational",
    "IngestHealth",
    "SearchIndex",
    "SearchHealth",
    "CollectionHealthResponse",
]

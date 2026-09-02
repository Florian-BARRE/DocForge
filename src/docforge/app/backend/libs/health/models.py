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
    """
    The rolled-up operational verdict of a collection — five honest states, not a binary up/down.

    Members:
        OPERATIONAL: Index populated, both graphs build, every used provider reachable.
        EMPTY: Providers reachable and graphs build, but nothing indexed yet — NEUTRAL (not a fault;
            a brand-new or still-ingesting collection reads this, never ``degraded``).
        DEGRADED: A provider actually used is unreachable/misconfigured — a real runtime fault.
        INGEST_UNAVAILABLE: The ingest pipeline is structurally invalid, so NEW documents cannot be
            ingested; an existing index stays searchable, so this is NOT a global outage.
        DOWN: Search itself cannot be served (broken search graph or unreachable query embedder).
    """

    OPERATIONAL = "operational"
    EMPTY = "empty"
    DEGRADED = "degraded"
    INGEST_UNAVAILABLE = "ingest_unavailable"
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
    verdict: HealthVerdict = Field(
        description="The rolled-up verdict: operational/empty/degraded/ingest_unavailable/down."
    )
    reason: str = Field(
        description="A human-readable, jargon-free first line explaining the verdict (the banner "
        "text). Any raw engine detail stays in ingest.build_error / search.build_error.",
    )
    checked_at: datetime = Field(description="When this probe ran (server time, UTC).")
    ingest: IngestHealth = Field(description="The ingest graph's buildability + provider sweep.")
    search: SearchHealth = Field(description="The search graph's buildability + provider sweep.")


class CollectionListVerdict(StrEnum):
    """
    The LIGHTWEIGHT, structural-only verdict the fleet LIST carries — three states, derived from the
    stored pipeline's buildability + cheap DB counters, WITHOUT any provider-reachability probe.

    Deliberately narrower than the detail's live ``HealthVerdict``: the network-dependent states
    (``degraded`` / ``down``) require probing every provider and stay EXCLUSIVELY on the on-demand
    detail endpoint (`GET /collections/{id}/health`). The list must be cheap and deterministic —
    rendering it must never sweep every provider of every collection on each page load.

    Members:
        EMPTY: The ingest pipeline builds, but nothing is chunked yet — NEUTRAL, ready to ingest.
        OPERATIONAL: The ingest pipeline builds and the collection has indexed content.
        CANNOT_INGEST: The stored ingest pipeline is structurally invalid — new documents cannot be
            ingested (the structural counterpart of the detail's ``ingest_unavailable``).
    """

    EMPTY = "empty"
    OPERATIONAL = "operational"
    CANNOT_INGEST = "cannot_ingest"


class CollectionHealthSummary(BaseModel):
    """
    The compact per-collection health the fleet LIST carries — a cheap, structural verdict plus fresh
    DB counters, computed server-side ONCE per list load (batched, no N+1, no provider probe, no
    Qdrant round-trip). It replaces the old N independent client-side ``/health`` probes that raced
    under concurrent load: the card now shows the SAME structural determination + the SAME counters as
    the collection's own overview, while the live provider sweep stays on the on-demand detail probe.
    """

    verdict: CollectionListVerdict = Field(
        description="The structural verdict: empty / operational / cannot_ingest (never the "
        "network-dependent degraded/down — those live on the on-demand detail probe)."
    )
    doc_count: int = Field(
        description="Number of documents in the collection (0 when none ingested yet)."
    )
    chunk_count: int = Field(
        description="Number of chunks indexed for the collection, read from Postgres (0 when none)."
    )
    last_ingest_at: datetime | None = Field(
        default=None,
        description="Finish time of the most recent successful ingest (None when there is none).",
    )


__all__ = [
    "HealthVerdict",
    "SearchOperational",
    "IngestHealth",
    "SearchIndex",
    "SearchHealth",
    "CollectionHealthResponse",
    "CollectionListVerdict",
    "CollectionHealthSummary",
]

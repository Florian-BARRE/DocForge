# ====== Code Summary ======
# Response models for the health resources, mirrored field-for-field from the DocForge backend router
# models: the bare-root liveness payload (HealthStatus) AND the on-demand collection-health probe
# (GET /collections/{id}/health) — the per-provider reachability sweep, index facts and the rolled-up
# 5-state verdict, plus the lightweight structural verdict/summary the collection LIST attaches to
# every item (no provider probe, batched DB counters only).

# ====== Standard Library Imports ======
from datetime import datetime
from enum import StrEnum
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# The tri-state search-operational signal: a plain bool for the clear cases plus the "degraded"
# middle (query embedder reachable but the index is empty, or a configured reranker is unreachable).
SearchOperational = bool | Literal["degraded"]


class HealthStatus(BaseModel):
    """
    The public health probe payload.

    Attributes:
        status (str): Liveness marker — always ``"ok"`` when the app is serving.
    """

    status: str = Field(description="Liveness marker — always 'ok' when the app is serving.")


class ProbeStatus(StrEnum):
    """
    The outcome of probing one provider-hosted node for reachability.

    Members:
        OK: The endpoint answered (any non-auth status) — reachable with accepted credentials.
        UNREACHABLE: The endpoint never answered (DNS/refused/timeout) or the probe timed out.
        AUTH_FAILED: The endpoint answered but rejected the credentials (HTTP 401/403).
        NOT_CONFIGURED: A provider that was expected in the graph is absent (nothing to probe).
        SKIPPED: A local action leaf with no endpoint to probe (no preflight override).
    """

    OK = "ok"
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "auth_failed"
    NOT_CONFIGURED = "not_configured"
    SKIPPED = "skipped"


class ProviderProbeResult(BaseModel):
    """
    One provider-hosted node's reachability outcome within a sweep.

    Attributes:
        node_id (str): The graph-unique id of the probed node.
        kind (str): The node's KIND within its family (e.g. bge_server, mistral).
        family (str | None): The registry family the node belongs to (e.g. embed, ocr, rerank).
        side (str): Which pipeline the node was swept in — 'ingest' or 'search'.
        status (ProbeStatus): The probe outcome.
        endpoint (str | None): The provider's probed base URL (secret-free — never the api_key);
            None when the leaf has no endpoint (skipped) or none is configured.
        detail (str | None): Human-readable reason for a non-ok status (None when ok).
        latency_ms (int | None): Probe round-trip in milliseconds (None when nothing was probed).
    """

    node_id: str = Field(description="The graph-unique id of the probed node.")
    kind: str = Field(description="The node's KIND within its family (e.g. bge_server, mistral).")
    family: str | None = Field(
        default=None, description="The registry family the node belongs to (e.g. embed, ocr, rerank)."
    )
    side: str = Field(description="Which pipeline the node was swept in: 'ingest' or 'search'.")
    status: ProbeStatus = Field(description="The probe outcome.")
    endpoint: str | None = Field(
        default=None,
        description="The provider's probed base URL (secret-free — never the api_key); None when "
        "the leaf has no endpoint (skipped) or none is configured.",
    )
    detail: str | None = Field(
        default=None, description="Human-readable reason for a non-ok status (None when ok)."
    )
    latency_ms: int | None = Field(
        default=None, description="Probe round-trip in milliseconds (None when nothing was probed)."
    )


class HealthVerdict(StrEnum):
    """
    The rolled-up operational verdict of a collection — five honest states, not a binary up/down.

    Members:
        OPERATIONAL: Index populated, both graphs build, every used provider reachable.
        EMPTY: Providers reachable and graphs build, but nothing indexed yet — NEUTRAL (not a fault).
        DEGRADED: A provider actually used is unreachable/misconfigured — a real runtime fault.
        INGEST_UNAVAILABLE: The ingest pipeline is structurally invalid — new documents cannot be
            ingested; an existing index stays searchable, so this is NOT a global outage.
        DOWN: Search itself cannot be served (broken search graph or unreachable query embedder).
    """

    OPERATIONAL = "operational"
    EMPTY = "empty"
    DEGRADED = "degraded"
    INGEST_UNAVAILABLE = "ingest_unavailable"
    DOWN = "down"


class IngestHealth(BaseModel):
    """
    The ingest graph's health: whether it builds and its provider reachability sweep.

    Attributes:
        buildable (bool): Whether the stored ingest blob heals, builds and structurally validates.
        build_error (str | None): The build/validation error when ``buildable`` is false.
        providers (list[ProviderProbeResult]): One reachability outcome per provider-hosted ingest
            action leaf.
    """

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
    """
    The retrieval index facts: how many vectors are stored and when they were last written.

    Attributes:
        vector_count (int): Number of vector points indexed (0 when never ingested).
        last_ingest_at (datetime | None): Finish time of the most recent successful ingest.
    """

    vector_count: int = Field(
        description="Number of vector points indexed for the collection (0 when never ingested)."
    )
    last_ingest_at: datetime | None = Field(
        default=None,
        description="Finish time of the most recent successful ingest (None when there is none).",
    )


class SearchHealth(BaseModel):
    """
    The search graph's health: buildability, provider sweep, index facts and the roll-up.

    Attributes:
        buildable (bool): Whether the collection's search blob (or the stock default) builds.
        search_operational (SearchOperational): true / false / 'degraded' — whether a query can
            actually be served now.
        build_error (str | None): The search-graph build/validation error when not buildable.
        providers (list[ProviderProbeResult]): The query embedder outcome plus the reranker's.
        index (SearchIndex): The collection's vector-index size + last ingest time.
    """

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
    """
    The full on-demand operational health of one collection.

    Attributes:
        collection_id (str): The probed collection's id.
        verdict (HealthVerdict): The rolled-up verdict.
        reason (str): A human-readable, jargon-free first line explaining the verdict.
        checked_at (datetime): When this probe ran (server time, UTC).
        ingest (IngestHealth): The ingest graph's buildability + provider sweep.
        search (SearchHealth): The search graph's buildability + provider sweep.
    """

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
    DB counters, computed server-side ONCE per list load (batched, no N+1, no provider probe).

    Attributes:
        verdict (CollectionListVerdict): The structural verdict.
        doc_count (int): Number of documents in the collection (0 when none ingested yet).
        chunk_count (int): Number of chunks indexed for the collection, read from Postgres.
        last_ingest_at (datetime | None): Finish time of the most recent successful ingest.
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
    "HealthStatus",
    "ProbeStatus",
    "ProviderProbeResult",
    "HealthVerdict",
    "IngestHealth",
    "SearchIndex",
    "SearchHealth",
    "CollectionHealthResponse",
    "CollectionListVerdict",
    "CollectionHealthSummary",
]

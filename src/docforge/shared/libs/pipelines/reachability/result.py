# ====== Code Summary ======
# ProviderProbeResult — the structured, per-node outcome of a reachability sweep. One entry per
# swept action leaf: which node (id/kind/family), on which side of the pipeline it was probed
# (ingest / search), the outcome (ProbeStatus), a human detail and the round-trip latency. It is a
# pure data record — the app process serialises it straight into the collection-health response.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .status import ProbeStatus


class ProviderProbeResult(BaseModel):
    """One provider-hosted node's reachability outcome within a sweep."""

    node_id: str = Field(description="The graph-unique id of the probed node.")
    kind: str = Field(description="The node's KIND within its family (e.g. bge_server, mistral).")
    family: str | None = Field(
        default=None,
        description="The registry family the node belongs to (e.g. embed, ocr, rerank).",
    )
    side: str = Field(
        description="Which pipeline the node was swept in: 'ingest' or 'search'.",
    )
    status: ProbeStatus = Field(description="The probe outcome.")
    endpoint: str | None = Field(
        default=None,
        description="The provider's probed base URL (secret-free — never the api_key); None when "
        "the leaf has no endpoint (skipped) or none is configured.",
    )
    detail: str | None = Field(
        default=None,
        description="Human-readable reason for a non-ok status (None when ok).",
    )
    latency_ms: int | None = Field(
        default=None,
        description="Probe round-trip in milliseconds (None when nothing was probed).",
    )


__all__ = ["ProviderProbeResult"]

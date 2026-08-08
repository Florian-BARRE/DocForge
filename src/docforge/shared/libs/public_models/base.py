# ====== Code Summary ======
# Base of the shared artefact vocabulary — the typed data that flows between pipeline nodes.
# A node's CONSUMES/PRODUCES faces reference these concrete artefact classes (DocumentIR,
# ChunkSet, …). The graph validator decides producer→consumer compatibility by a plain subclass
# relationship over them, so keeping every artefact under one base keeps that check honest.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field


class Artifact(BaseModel):
    """
    Base class for every shared data artefact exchanged between nodes.

    Concrete artefacts subclass this and live alongside it in shared/libs/public_models. They
    are referenced by node I/O faces and compared by subclass relationship during graph
    validation.
    """


class NodeConfig(BaseModel):
    """
    Base class for a node's CONFIG face (the serialized, UI-editable knobs).

    Lives in public_models (the bottom vocabulary layer) so config value-objects that are also
    embedded in artefacts (e.g. OpenAICompatConfig, carried by a GenerationRequest) need no
    upward import into the pipelines layer.

    extra="forbid" is the point: a typo in a stored pipeline blob ("do_ocrr") must fail the build
    loudly instead of being silently ignored — a config the user believes is set MUST be applied.
    """

    model_config = ConfigDict(extra="forbid")


class TimeoutConfig(NodeConfig):
    """
    The shared network-TIMEOUT surface every network-calling node config mixes in.

    Before this, ``timeout_seconds`` was re-declared ad hoc on each provider config. Mixing this in
    gives every network node the SAME per-request timeout plus a DEDICATED preflight budget, so the
    pre-spend reachability probe is bounded independently of a long real-request timeout.

    Retry-agnostic on purpose: a node that gives up rather than retries (the reranker degrades to
    fusion order) mixes in THIS surface and gains no inert retry knob. Nodes that DO retry mix in
    ``TimeoutRetryConfig`` instead.

    Every field carries a default, so a stored blob that predates these keys still builds cleanly
    under ``extra="forbid"``. A family overrides only the DEFAULT it needs (e.g. a 120 s converter
    timeout) by re-declaring the field — the knob stays the same, only its default moves.
    """

    timeout_seconds: float = Field(
        default=30.0, gt=0, description="Per-request timeout for the node's network call (s)."
    )
    preflight_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        description="Per-attempt timeout for the pre-spend reachability probe (s), independent of "
        "the real-request timeout so a long generation timeout never stalls preflight.",
    )


class TimeoutRetryConfig(TimeoutConfig):
    """
    ``TimeoutConfig`` + a bounded transient-retry policy, for every network node that retries.

    Adds the two retry knobs on top of the shared timeout surface. Each retrying family keeps its
    own retry defaults (e.g. embed 3, vlm 1) by re-declaring the field.
    """

    max_retries: int = Field(
        default=2,
        ge=0,
        description="Retries on a TRANSIENT provider error (timeout/transport/429/5xx) before "
        "giving up and letting the graph escalate. Consumed by every retrying node: forwarded to the "
        "provider SDK client for chat/embeddings nodes, or driving the shared retry loop (direct-HTTP "
        "nodes) and the vlm/embed hand-loops. 0 disables retry.",
    )
    retry_backoff_seconds: float = Field(
        default=1.0,
        gt=0,
        description="Base delay for the linear backoff of the SHARED retry loop and the vlm/embed "
        "hand-loops (delay = base * attempt). Chat/embeddings SDK-client nodes use the provider "
        "SDK's own backoff schedule, so this knob does not apply to them.",
    )


__all__ = ["Artifact", "NodeConfig", "TimeoutConfig", "TimeoutRetryConfig"]

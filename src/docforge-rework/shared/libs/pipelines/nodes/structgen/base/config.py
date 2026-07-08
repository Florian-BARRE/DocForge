# ====== Code Summary ======
# StructGenConfig — the config of a structgen step. A structured-generation call takes its primary
# endpoint from the REQUEST (resolved by the prep node from the contract targets), so a step needs no
# endpoint at all: its config is an OPTIONAL endpoint OVERRIDE, empty by default. This is the chain
# seam — the head step leaves it empty (it uses the request's per-field endpoint), and a fallback
# step sets a concrete robust endpoint that wins over the request's. Everything else that shapes the
# call (system prompt, text, temperature, max_tokens) travels on the request, not here.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig


class StructGenConfig(NodeConfig):
    """Optional endpoint override for one structgen step (empty = use the request's endpoint)."""

    base_url: str = Field(
        default="",
        description="Endpoint override; empty = use the request's endpoint (the chain-head default).",
    )
    api_key: str = Field(default="", description="API key override; empty = the request's key.")
    model: str = Field(default="", description="Model override; empty = the request's model.")
    timeout_seconds: float = Field(
        default=0.0, ge=0.0, description="Per-request timeout override (s); 0 = the request's timeout."
    )


__all__ = ["StructGenConfig"]

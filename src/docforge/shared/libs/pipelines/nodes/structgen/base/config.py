# ====== Code Summary ======
# StructGenConfig — the config of a structgen step. A structured-generation call takes its primary
# endpoint from the REQUEST (resolved by the prep node from the contract targets), so a step needs no
# endpoint at all: its config is an OPTIONAL endpoint OVERRIDE, empty by default. This is the chain
# seam — the head step leaves it empty (it uses the request's per-field endpoint), and a fallback
# step sets a concrete robust endpoint that wins over the request's. Everything else that shapes the
# call (system prompt, text, temperature, max_tokens) travels on the request, not here — except an
# optional per-step ``seed``, a deployment knob for reproducibility that has no place on the request.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import TimeoutRetryConfig


class StructGenConfig(TimeoutRetryConfig):
    """Optional endpoint override for one structgen step (empty = use the request's endpoint).

    Timeout/retry come from ``TimeoutRetryConfig``, but ``timeout_seconds`` KEEPS its 0-means-inherit
    override semantics (0 = use the request's timeout). ``max_retries`` is forwarded to the LangChain
    client in the openai-compatible step.
    """

    base_url: str = Field(
        default="",
        description="Endpoint override; empty = use the request's endpoint (the chain-head default).",
    )
    api_key: str = Field(default="", description="API key override; empty = the request's key.")
    model: str = Field(default="", description="Model override; empty = the request's model.")
    timeout_seconds: float = Field(
        default=0.0,
        ge=0.0,
        description="Per-request timeout override (s); 0 = the request's timeout.",
    )
    seed: int | None = Field(
        default=None,
        description="Optional sampling seed forwarded to the endpoint; None = unpinned (the "
        "provider's default). Set it to pin reproducible generations on a deployment.",
    )


__all__ = ["StructGenConfig"]

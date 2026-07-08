# ====== Code Summary ======
# MetagenPrepConfig — the config of a metagen PREP node. It is today's BaseMetagenConfig MINUS the
# two knobs that become graph mechanics once the model call is externalised into a structgen chain:
# ``on_error`` (a fail-soft skip terminal is now a graph EDGE, not a node flag) and ``max_concurrency``
# (moves onto the ForEach that runs the per-item chain). Everything a prep needs to SHAPE the calls it
# emits lives here: the default endpoint (the fields carried onto each GenerationRequest), the per-field
# TARGETS (prompt + endpoint override), the grouping knob (one call per endpoint or one per field), the
# system prompt, and the generation caps.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import OpenAICompatConfig

# ====== Local Project Imports ======
from ..base import DEFAULT_METAGEN_PROMPT, MetagenGrouping, MetagenTarget


class MetagenPrepConfig(OpenAICompatConfig):
    """Shared metagen-prep config — the default endpoint plus the per-field bindings and call shape."""

    targets: list[MetagenTarget] = Field(
        default_factory=list,
        description="Per-field bindings; empty = every GENERATED field of this node's scope, "
        "auto prompts, default endpoint.",
    )
    grouping: MetagenGrouping = Field(
        default=MetagenGrouping.COMBINED,
        description="combined: fields sharing an endpoint asked in one structured call; "
        "per_field: one call per field.",
    )
    system_prompt: str = Field(
        default=DEFAULT_METAGEN_PROMPT, description="The generation instruction carried on each request."
    )
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature.")
    max_tokens: int = Field(default=512, gt=0, description="Generation cap per structured call.")
    max_document_words: int = Field(
        default=4000, gt=0,
        description="Hard cap on the document text handed to the model (document scope; truncated).",
    )


__all__ = ["MetagenPrepConfig"]

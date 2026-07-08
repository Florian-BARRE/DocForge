# ====== Code Summary ======
# MetagenPrepConfig — the config of a metagen PREP node, which doubles as the metagen STAGE config the
# studio edits. It carries everything a prep needs to SHAPE the calls it emits (the default endpoint
# each GenerationRequest inherits, the per-field TARGETS, the grouping knob, the system prompt and the
# generation caps) PLUS the two STAGE-EXECUTION knobs — ``on_error`` and ``max_concurrency`` — that
# became graph mechanics when the model call was externalised into a structgen chain. Those two are NOT
# consumed by the prep's run(): they are read by the stage assembler to shape the ForEach the prep is
# wrapped in (its concurrency) and the fail-soft skip terminal of its body (the on_error edge). Parking
# them on the stage's anchor node keeps them user-editable through the very same config the view exposes.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import OpenAICompatConfig

# ====== Local Project Imports ======
from ..base import DEFAULT_METAGEN_PROMPT, MetagenGrouping, MetagenOnError, MetagenTarget


class MetagenPrepConfig(OpenAICompatConfig):
    """Shared metagen-prep config — the default endpoint, the per-field bindings and the stage knobs."""

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
    max_concurrency: int = Field(
        default=4, ge=1,
        description="Stage knob (read by the assembler): how many requests the ForEach runs at once.",
    )
    on_error: MetagenOnError = Field(
        default=MetagenOnError.SKIP_FIELDS,
        description="Stage knob (read by the assembler): skip_fields wires a fail-soft skip terminal "
        "so a failed request drops its fields; fail lets the failure propagate as an item failure.",
    )


__all__ = ["MetagenPrepConfig"]

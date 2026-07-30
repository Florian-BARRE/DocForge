# ====== Code Summary ======
# Config of the metagen family. The CONTRACT declares the generated fields (name, type, scope);
# this config decides HOW each one is filled: per-field TARGETS bind a prompt and (optionally)
# their own LLM endpoint, on top of the node's default endpoint. The grouping knob decides the
# call shape: fields sharing an endpoint asked TOGETHER (one structured object) or one call per
# field. The field TYPE always forces the model output through a structured-output schema.

# ====== Standard Library Imports ======
from enum import StrEnum

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import OpenAICompatConfig

# The generation instruction: faithful extraction, structured output does the shaping.
DEFAULT_METAGEN_PROMPT = (
    "You extract structured metadata from document text. Fill every requested field faithfully "
    "from the text; leave a field null only when the text truly lacks the information."
)


class MetagenGrouping(StrEnum):
    """Call shape — the cost/isolation knob (user-set, per node)."""

    COMBINED = "combined"  # fields sharing an endpoint are asked in ONE structured object
    PER_FIELD = "per_field"  # one call per field (max isolation, N× the spend)


class MetagenOnError(StrEnum):
    """What a failed or unusable generation does."""

    SKIP_FIELDS = "skip_fields"  # the affected fields stay absent (logged); the run continues
    FAIL = "fail"  # the node fails (strict runs)


class MetagenTarget(BaseModel):
    """
    The per-field binding: which contract field, with which prompt, on which model.

    Attributes:
        field (str): The GENERATED contract field this target fills (must match the node scope).
        prompt (str): Field instruction; empty = auto-derived from the field's name and type.
        base_url (str): Endpoint override; empty = the node's default endpoint.
        api_key (str): Key override; empty = the node's default.
        model (str): Model override; empty = the node's default.
    """

    model_config = ConfigDict(extra="forbid")

    field: str
    prompt: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class BaseMetagenConfig(OpenAICompatConfig):
    """Shared metagen config — the default endpoint + the per-field bindings."""

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
        default=DEFAULT_METAGEN_PROMPT, description="The generation instruction."
    )
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature.")
    max_tokens: int = Field(default=512, gt=0, description="Generation cap per structured call.")
    max_document_words: int = Field(
        default=4000,
        gt=0,
        description="Hard cap on the text handed to the model (truncated from the start).",
    )
    max_concurrency: int = Field(
        default=4, ge=1, description="Simultaneous model calls (chunk scope)."
    )
    on_error: MetagenOnError = Field(
        default=MetagenOnError.SKIP_FIELDS,
        description="Failure policy: skip the affected fields (default) or fail the node.",
    )


__all__ = [
    "BaseMetagenConfig",
    "MetagenTarget",
    "MetagenGrouping",
    "MetagenOnError",
    "DEFAULT_METAGEN_PROMPT",
]

# ====== Code Summary ======
# The stage LAYER's data contracts — the simple product-level view over the graph pipeline and the
# actions that mutate it. StageCatalog is the whole ordered skeleton (disabled stages present with
# enabled=False, so the UI shows the full rail greyed where off). A StageView describes one stage:
# its interaction face (StageKind), its current provider/config, the model-call chains (enrich) and
# the ordered method stack (contextualize). StageAction is the discriminated union of everything the
# user can do: toggle a stage, pick a provider, edit a config, build a fallback chain, order a
# stack. Every field is described — the backend-driven UI carries zero hardcoded pipeline text.

# ====== Standard Library Imports ======
from typing import Annotated, Any, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# ====== Local Project Imports ======
from .spec import StageKind


class ChainStep(BaseModel):
    """
    One provider in a fallback chain — a single model-call attempt.

    Every step falls through to the NEXT step on failure; ``score_below`` adds a quality
    escalation (take the next step when this one's score is under the threshold). The last step
    has the final say.

    Attributes:
        kind (str): Registry kind within the chain's family (e.g. ``rapidocr``, ``mistral``).
        config (dict): The provider's config (endpoint, key, prompt…).
        score_below (float | None): Escalate to the next step when this step's score is below
            this threshold; null means fall through on failure only (or the step is terminal).
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(description="Registry kind within the chain's family.")
    config: dict[str, Any] = Field(
        default_factory=dict, description="The provider's config (endpoint, key, prompt…)."
    )
    score_below: float | None = Field(
        default=None,
        description="Escalate to the next step when the score is below this; null = on failure only.",
    )


class ChainView(BaseModel):
    """
    A fallback chain the user can build at one model-call site of a stage.

    Flagged with its family so the UI can colour chains distinctly from the linear stage rail.

    Attributes:
        slot (str): Stable slot key of the model-call site (e.g. ``scanned_text_ocr``).
        title (str): Human label of the site.
        description (str): What this model call is for.
        family (str): The model family the chain draws from (``ocr`` / ``vlm`` / ``llm``).
        available (list[str]): The registry kinds available in the family (the step choices).
        steps (list[ChainStep]): The ordered providers of the chain (cheap → robust).
    """

    slot: str = Field(description="Stable slot key of the model-call site.")
    title: str = Field(description="Human label of the model-call site.")
    description: str = Field(description="What this model call is for.")
    family: str = Field(description="The model family the chain draws from (ocr / vlm / llm).")
    available: list[str] = Field(
        default_factory=list, description="Registry kinds available in the family (step choices)."
    )
    steps: list[ChainStep] = Field(
        default_factory=list, description="The ordered providers of the chain (cheap → robust)."
    )


class StackMethod(BaseModel):
    """
    One method of a stackable stage — a node in the ordered composition.

    Attributes:
        kind (str): Registry kind within the stack's family (e.g. ``doc_meta``, ``breadcrumb``).
        config (dict): The method's config.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(description="Registry kind within the stack's family.")
    config: dict[str, Any] = Field(default_factory=dict, description="The method's config.")


class StageView(BaseModel):
    """
    The product-level view of one pipeline stage — everything the UI renders for it.

    Attributes:
        key (str): Stable stage key.
        title (str): Human label.
        description (str): What the stage does.
        kind (StageKind): Interaction face (fixed / toggle / provider / stack).
        enabled (bool): Whether the stage is currently part of the pipeline.
        removable (bool): Whether the stage can be toggled off (fixed stages are False).
        family (str | None): The registry family the stage draws its node(s) from.
        provider (str | None): The currently selected kind (provider stages).
        available (list[str]): The kinds offered by the family (provider stages).
        config (dict | None): The current node config (single-config stages; None otherwise).
        chains (list[ChainView]): The per-site model chains (enrich; empty elsewhere).
        stack (list[StackMethod]): The ordered methods (contextualize; empty elsewhere).
        requires (list[str]): Keys of the stages this one depends on.
        notes (str | None): A caveat shown to the user (e.g. a required config to fill).
    """

    key: str = Field(description="Stable stage key.")
    title: str = Field(description="Human label of the stage.")
    description: str = Field(description="What the stage does.")
    kind: StageKind = Field(description="Interaction face (fixed / toggle / provider / stack).")
    enabled: bool = Field(description="Whether the stage is currently part of the pipeline.")
    removable: bool = Field(description="Whether the stage can be toggled off.")
    family: str | None = Field(
        default=None, description="The registry family the stage draws its node(s) from."
    )
    provider: str | None = Field(
        default=None, description="The currently selected kind (provider stages)."
    )
    available: list[str] = Field(
        default_factory=list, description="The kinds offered by the family (provider stages)."
    )
    config: dict[str, Any] | None = Field(
        default=None, description="The current node config (single-config stages)."
    )
    chains: list[ChainView] = Field(
        default_factory=list, description="The per-site model chains (enrich; empty elsewhere)."
    )
    stack: list[StackMethod] = Field(
        default_factory=list, description="The ordered methods (contextualize; empty elsewhere)."
    )
    requires: list[str] = Field(
        default_factory=list, description="Keys of the stages this one depends on."
    )
    notes: str | None = Field(default=None, description="A caveat shown to the user.")


class StageCatalog(BaseModel):
    """
    The full ordered skeleton — every canonical stage, disabled ones present with enabled=False.

    Attributes:
        stages (list[StageView]): The stages in run order (the vertical rail the UI renders).
    """

    stages: list[StageView] = Field(
        default_factory=list, description="The stages in run order (the vertical rail)."
    )


class EnableStage(BaseModel):
    """Turn a removable stage on (enabling its dependencies too)."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["enable_stage"] = "enable_stage"
    stage: str = Field(description="Key of the stage to enable.")


class DisableStage(BaseModel):
    """Turn a removable stage off (cascading to the stages that depend on it)."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["disable_stage"] = "disable_stage"
    stage: str = Field(description="Key of the stage to disable.")


class SetProvider(BaseModel):
    """Pick the provider of an exclusive stage — swap the kind, reset its config to defaults."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["set_provider"] = "set_provider"
    stage: str = Field(description="Key of the provider stage.")
    kind: str = Field(description="The registry kind to select within the stage's family.")


class SetStageConfig(BaseModel):
    """Replace a stage node's config (whole-dict replacement, like the graph editor's set_config)."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["set_config"] = "set_config"
    stage: str = Field(description="Key of the stage whose config is replaced.")
    node: str | None = Field(
        default=None,
        description="Id of the target node inside a multi-node stage; null = the stage's primary "
        "node (e.g. metagen's chunk/document node, intake's convert node).",
    )
    config: dict[str, Any] = Field(description="The new config dict (full replacement).")


class SetChain(BaseModel):
    """Rebuild a fallback chain — an enrich per-figure site, or a chain-capable stage itself."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["set_chain"] = "set_chain"
    stage: str = Field(description="Key of the stage owning the chain (enrich, or a provider stage).")
    slot: str | None = Field(
        default=None,
        description="Slot key of an enrich model-call site (e.g. scanned_text_ocr); null = the "
        "stage itself is the chain site (e.g. parse).",
    )
    steps: list[ChainStep] = Field(
        description="The ordered providers of the chain (cheap → robust; last has the final say)."
    )


class SetStack(BaseModel):
    """Rebuild the ordered method stack of a stackable stage (contextualize)."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["set_stack"] = "set_stack"
    stage: str = Field(description="Key of the stackable stage (contextualize).")
    steps: list[StackMethod] = Field(
        description="The methods in application order (empty disables the stage)."
    )


# Discriminated union — the server selects the action from its ``action`` tag on load.
type StageAction = Annotated[
    EnableStage
    | DisableStage
    | SetProvider
    | SetStageConfig
    | SetChain
    | SetStack,
    Field(discriminator="action"),
]


__all__ = [
    "ChainStep",
    "ChainView",
    "StackMethod",
    "StageView",
    "StageCatalog",
    "EnableStage",
    "DisableStage",
    "SetProvider",
    "SetStageConfig",
    "SetChain",
    "SetStack",
    "StageAction",
]

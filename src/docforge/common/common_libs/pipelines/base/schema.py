# ====== Code Summary ======
# NodeSchema — the self-describing shape a node's describe() emits, recursing into children. It is
# the single recursive structure the /discovery API (and later the UI) renders to show the whole
# tree (pipeline -> stages -> steps) with its dependencies and required capabilities, with zero
# hardcoded text. Pure Pydantic, no behaviour.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class ProviderSchema(BaseModel):
    """
    One configurable provider in a chain's catalog.

    Attributes:
        id (str): Provider discriminator (e.g. ``"paddle_ocr"``, ``"mistral_ocr"``).
        config_schema (dict): JSON schema of the provider's per-collection config (URL, model, …).
    """

    id: str = Field(description="Provider id (discriminator).")
    config_schema: dict = Field(description="JSON schema of the provider config.")


class ChainSchema(BaseModel):
    """
    A node's chain SLOT, self-described for the discovery UI.

    A chain is configured per collection by choosing + ordering providers (from the catalog) and
    setting the escalation gate. This is the "possibilities" the UI renders — never a built chain.

    Attributes:
        name (str): Service name the built chain is injected under (e.g. ``"ocr_chain"``).
        category (str): Provider category (``"ocr"`` / ``"vlm"`` / ``"parser"`` / …).
        gate_schema (dict): JSON schema of the escalation gate config (min_score, failure_policy, …).
        providers (list[ProviderSchema]): The catalog of providers available for this category.
    """

    name: str = Field(description="Injected service name of the built chain.")
    category: str = Field(description="Provider category this chain serves.")
    gate_schema: dict = Field(description="JSON schema of the chain escalation gate config.")
    providers: list[ProviderSchema] = Field(
        default_factory=list, description="Catalog of providers available for the category."
    )


class NodeSchema(BaseModel):
    """
    Self-description of a single node — recurses into its children.

    Attributes:
        kind (str): Node level (``"pipeline"`` / ``"stage"`` / ``"step"``).
        key (str): Stable node identifier (unique among siblings).
        name (str): Human-readable node name.
        description (str): One-line description.
        consumes (list[str]): Keys of the sibling nodes whose output this node consumes (the edges).
        requires (list[str]): Names of the capabilities this node requires.
        config_schema (dict | None): JSON schema of the node's per-collection Config (None when the
            node has no configurable knobs) — the discovery UI renders the editing form from it.
        children (list[NodeSchema]): Child schemas, in declaration order.
    """

    kind: str = Field(description="Node level: pipeline / stage / step.")
    key: str = Field(description="Stable node identifier, unique among siblings.")
    name: str = Field(description="Human-readable node name.")
    description: str = Field(default="", description="One-line description of the node.")
    consumes: list[str] = Field(default_factory=list, description="Sibling keys consumed.")
    requires: list[str] = Field(default_factory=list, description="Required capability names.")
    config_schema: dict | None = Field(default=None, description="JSON schema of the node config.")
    chains: list[ChainSchema] = Field(
        default_factory=list, description="Chain slots (each with its gate + provider catalog)."
    )
    children: list["NodeSchema"] = Field(default_factory=list, description="Child node schemas.")


NodeSchema.model_rebuild()


__all__ = ["NodeSchema", "ChainSchema", "ProviderSchema"]

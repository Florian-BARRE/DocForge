# ====== Code Summary ======
# NodeSchema — the self-describing shape a node's describe() emits, recursing into children. It is
# the single recursive structure the /discovery API (and later the UI) renders to show the whole
# tree (pipeline -> stages -> steps) with its dependencies and required capabilities, with zero
# hardcoded text. Pure Pydantic, no behaviour.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


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
        children (list[NodeSchema]): Child schemas, in declaration order.
    """

    kind: str = Field(description="Node level: pipeline / stage / step.")
    key: str = Field(description="Stable node identifier, unique among siblings.")
    name: str = Field(description="Human-readable node name.")
    description: str = Field(default="", description="One-line description of the node.")
    consumes: list[str] = Field(default_factory=list, description="Sibling keys consumed.")
    requires: list[str] = Field(default_factory=list, description="Required capability names.")
    children: list["NodeSchema"] = Field(default_factory=list, description="Child node schemas.")


NodeSchema.model_rebuild()


__all__ = ["NodeSchema"]

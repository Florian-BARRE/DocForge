# ====== Code Summary ======
# The self-describing shape a node's describe() emits — the clean JSON the frontend renders to build a
# pipeline (and the builder re-instantiates). It is the whole tree in the graph vocabulary: per node
# its id + kind + config schema, and for a group its child nodes + the transitions (edges with their
# conditions) wiring them. Pure Pydantic, no behaviour: a pipeline is fully described by data.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .enums import Condition, NodeKind


class TransitionSchema(BaseModel):
    """A described edge: ``source -> target`` with its firing condition."""

    source: str = Field(description="Id of the node the edge leaves.")
    target: str = Field(description="Id of the node the edge enters.")
    when: Condition = Field(description="The condition that fires the edge.")
    threshold: float = Field(default=0.0, description="Score threshold (used by score_below).")


class NodeSchema(BaseModel):
    """
    Self-description of a single node — recurses into a group's children.

    Attributes:
        id (str): The node id.
        kind (NodeKind): ``action`` or ``group``.
        config_schema (dict | None): JSON schema of the node's per-collection Config (None when none).
        nodes (list[NodeSchema]): Child node schemas (a group only).
        transitions (list[TransitionSchema]): The edges wiring the children (a group only).
    """

    id: str = Field(description="Node id.")
    kind: NodeKind = Field(description="Node kind: action | group.")
    config_schema: dict | None = Field(default=None, description="JSON schema of the node config.")
    nodes: list["NodeSchema"] = Field(default_factory=list, description="Child node schemas.")
    transitions: list[TransitionSchema] = Field(
        default_factory=list, description="Edges wiring the children."
    )


NodeSchema.model_rebuild()


__all__ = ["TransitionSchema", "NodeSchema"]

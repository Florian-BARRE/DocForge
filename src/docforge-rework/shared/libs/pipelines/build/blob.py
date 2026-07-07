# ====== Code Summary ======
# The serialised form of a pipeline graph — the "blob" produced by the UI and stored in the DB.
# It mirrors a Group's declarative structure: nodes (an action or a nested group), the transitions
# between them, and the bindings that feed each node's input. An action node carries a raw config
# dict that the builder validates against the registered class. Reuses Transition + Binding from
# base. This module is pure data — the PipelineBuilder turns a blob into live node instances.
#
# Action, group and foreach blobs have DISTINCT shapes (family/kind vs nodes vs over/body), so
# with extra="forbid" a smart union resolves them by structure — no explicit discriminator needed,
# and node_type stays a plain NodeType field.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import Binding, NodeType, Transition


class ActionNodeBlob(BaseModel):
    """
    Serialised action node: which registered class to build, and its raw config.

    Attributes:
        node_type (NodeType): The node kind (ACTION).
        id (str): Graph-unique identifier.
        family (str): Registry family (e.g. ``"llm"``).
        kind (str): Registry kind within the family (e.g. ``"mistral"``).
        config (dict): Raw config, validated against the class's Config model at build time.
    """

    model_config = ConfigDict(extra="forbid")

    node_type: NodeType = NodeType.ACTION
    id: str
    family: str
    kind: str
    config: dict[str, Any] = Field(default_factory=dict)


# A node blob is an action, a nested group, or a foreach. Declared here (a lazy PEP 695 alias)
# BEFORE the recursive classes so they can reference it unquoted despite the recursion.
type NodeBlob = ActionNodeBlob | GroupNodeBlob | ForEachNodeBlob


class GroupNodeBlob(BaseModel):
    """
    Serialised group: its children (action or nested group), transitions and bindings.

    Attributes:
        node_type (NodeType): The node kind (GROUP).
        id (str): Graph-unique identifier.
        nodes (list[NodeBlob]): Child node blobs.
        transitions (list[Transition]): Control-flow edges between the children.
        bindings (dict[str, dict[str, Binding]]): Data wiring, keyed by child id then slot name.
    """

    model_config = ConfigDict(extra="forbid")

    node_type: NodeType = NodeType.GROUP
    id: str
    nodes: list[NodeBlob] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    bindings: dict[str, dict[str, Binding]] = Field(default_factory=dict)


class ForEachNodeBlob(BaseModel):
    """
    Serialised foreach: the list to iterate, how each item is exposed, and the per-item body.

    Attributes:
        node_type (NodeType): The node kind (FOREACH).
        id (str): Graph-unique identifier.
        over (Binding): Where the iterated list comes from (a ``list[...]`` field upstream).
        item_field (str): Group-input field each item is exposed under to the body.
        max_concurrency (int): How many items may run their body at the same time.
        body (GroupNodeBlob): The sub-graph run once per item.
    """

    model_config = ConfigDict(extra="forbid")

    node_type: NodeType = NodeType.FOREACH
    id: str
    over: Binding
    item_field: str
    max_concurrency: int = Field(default=4, ge=1)
    body: GroupNodeBlob


# Resolve the recursive references (GroupNodeBlob.nodes -> NodeBlob -> Group/ForEach blobs).
GroupNodeBlob.model_rebuild()
ForEachNodeBlob.model_rebuild()


__all__ = ["ActionNodeBlob", "GroupNodeBlob", "ForEachNodeBlob", "NodeBlob"]

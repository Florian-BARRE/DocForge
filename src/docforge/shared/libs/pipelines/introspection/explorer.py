# ====== Code Summary ======
# The explorer — describes a BUILT pipeline (a live Group) as a recursive tree the UI can render
# and edit. Each node is wrapped in an ExploredNode: its TYPE card (describe()) plus its instance
# data — the id, the current config values (action nodes), and for groups the child subtree, the
# transitions and the bindings. Combined with the palette (catalog), the UI has everything: what
# exists, what is wired, and with which values — zero hardcoded text.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    AbstractNode,
    ActionNode,
    Binding,
    ForEach,
    Group,
    NodeDescription,
    Transition,
)


class ExploredNode(BaseModel):
    """
    One node of a built pipeline, described for the UI (recursive for groups).

    Attributes:
        id (str): The node's graph-unique id.
        description (NodeDescription): Its type card (labels, config schema, I/O).
        config (dict | None): Current config values for an action node; None for a group.
        children (list[ExploredNode]): The child subtree when the node is a group.
        transitions (list[Transition]): The group's control-flow edges (groups only).
        bindings (dict[str, dict[str, Binding]]): The group's data wiring (groups only).
    """

    id: str
    description: NodeDescription
    config: dict[str, Any] | None = None
    # Genuine self-reference (the tree recurses): a quoted forward ref is the clean idiom here — a
    # class cannot name itself unquoted in its own body without `from __future__` (which is banned).
    children: list["ExploredNode"] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    bindings: dict[str, dict[str, Binding]] = Field(default_factory=dict)


class PipelineExplorer:
    """Static builder of the recursive description of a built pipeline."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("PipelineExplorer is a static-only class and cannot be instantiated.")

    @classmethod
    def explore(cls, node: AbstractNode) -> ExploredNode:
        """
        Describe a built node (and its subtree, if a group) for the UI.

        Args:
            node (AbstractNode): The graph root (or any node) to describe.

        Returns:
            ExploredNode: The recursive description — type cards + instance data.

        Raises:
            TypeError: If the node is neither an action node nor a group.
        """
        # 1. A group: wrap its card with its children subtree + wiring.
        if isinstance(node, Group):
            return ExploredNode(
                id=node.id,
                description=node.describe(),
                children=[cls.explore(child) for child in node.children],
                transitions=node.transitions,
                bindings=node.bindings,
            )

        # 2. A foreach: its loop wiring as config, its body as the single child subtree.
        if isinstance(node, ForEach):
            return ExploredNode(
                id=node.id,
                description=node.describe(),
                config={
                    "over": node.over.model_dump(mode="json"),
                    "item_field": node.item_field,
                    "max_concurrency": node.max_concurrency,
                },
                children=[cls.explore(node.body)],
            )

        # 3. An action node: wrap its card with its current config values.
        if isinstance(node, ActionNode):
            return ExploredNode(
                id=node.id,
                description=node.describe(),
                config=node.config.model_dump(mode="json"),
            )

        raise TypeError(f"Cannot explore unsupported node type: {type(node).__name__}")


__all__ = ["ExploredNode", "PipelineExplorer"]

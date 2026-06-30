# ====== Code Summary ======
# The two node types of the flow tree. Node is the shared base (an id + its kind). ActionNode is a
# leaf — one elementary unit of work exposing ``execute``. GroupNode contains child nodes wired by
# transitions; its behaviour (sequence vs escalation vs fallback) is NOT a subclass — it EMERGES from
# the conditions on its transitions, so the same class expresses every control shape. A group exposes
# its children, its entry node (where the flow starts), and the outgoing edges of any child.

# ====== Standard Library Imports ======
from abc import ABC, abstractmethod
from typing import Any, ClassVar

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .enums import NodeKind
from .transition import Transition


class Node(ABC, LoggerClass):
    """Shared base of every flow node — an identity and its kind. Pure: it never drives itself."""

    KIND: ClassVar[NodeKind]

    def __init__(self, node_id: str) -> None:
        """
        Args:
            node_id (str): The node's id, unique among its siblings (the transition endpoints).
        """
        LoggerClass.__init__(self)
        self.id = node_id


class ActionNode(Node):
    """A leaf node — one elementary unit of work. Concrete actions implement ``execute``."""

    KIND = NodeKind.ACTION

    @abstractmethod
    async def execute(self, data: Any) -> Any:
        """
        Perform the action on its input and return its output.

        Args:
            data (Any): The node's input (its predecessor's output, or the group input).

        Returns:
            Any: The node's output (may carry a ``score`` consumed by a ``score_below`` edge).
        """
        ...


class GroupNode(Node):
    """
    A node containing child nodes wired by transitions; its control shape emerges from the edges.

    All-``always`` edges -> a sequence; ``score_below`` edges -> an escalation (the old chain);
    ``on_failure`` edges -> a fallback. The flow starts at ``entry`` and follows the first firing
    outgoing edge of each node until a node has no firing edge (the terminal).
    """

    KIND = NodeKind.GROUP

    def __init__(
        self, node_id: str, nodes: list[Node], transitions: list[Transition], entry: str | None = None
    ) -> None:
        """
        Args:
            node_id (str): The group's id.
            nodes (list[Node]): The child nodes (actions or nested groups), in declaration order.
            transitions (list[Transition]): The edges wiring the children.
            entry (str | None): The id of the node where the flow starts (defaults to the first child).
        """
        Node.__init__(self, node_id)
        self._nodes: dict[str, Node] = {n.id: n for n in nodes}
        self._order: list[str] = [n.id for n in nodes]
        self.transitions: list[Transition] = list(transitions)
        self.entry: str = entry or self._order[0]

    @property
    def nodes(self) -> list[Node]:
        """The child nodes in declaration order."""
        return [self._nodes[node_id] for node_id in self._order]

    def node(self, node_id: str) -> Node:
        """Return a child node by id."""
        return self._nodes[node_id]

    def outgoing(self, node_id: str) -> list[Transition]:
        """Return the transitions leaving a child node, in declaration order (first-firing wins)."""
        return [t for t in self.transitions if t.source == node_id]


__all__ = ["Node", "ActionNode", "GroupNode"]

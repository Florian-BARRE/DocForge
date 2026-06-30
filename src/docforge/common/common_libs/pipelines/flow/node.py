# ====== Code Summary ======
# The two node types of the flow tree. Node is the shared base: an id + its kind + the typed IO it
# declares (Input/Output). ActionNode is a leaf — one elementary unit of work whose ``execute`` reads
# its resolved Input + the injected services from the Context. GroupNode contains child nodes wired by
# transitions; its behaviour (sequence vs escalation vs fallback) EMERGES from the conditions on its
# edges, not from a subclass. A group turns its children's outputs into its own typed Output via
# ``assemble`` (default: the terminal node's output — the natural shape for an escalation).

# ====== Standard Library Imports ======
from abc import ABC, abstractmethod
from typing import ClassVar

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from pydantic import BaseModel

# ====== Local Project Imports ======
from .context import Context
from .enums import NodeKind
from .io import NodeInput, NodeOutput
from .schema import NodeSchema, TransitionSchema
from .transition import Transition


class Node(ABC, LoggerClass):
    """Shared base of every flow node — an identity, its kind, and its typed IO contract."""

    KIND: ClassVar[NodeKind]
    Input: ClassVar[type[NodeInput]] = NodeInput
    Output: ClassVar[type[NodeOutput]] = NodeOutput
    # The node's per-collection config (a Pydantic model); None when the node has no configurable knobs.
    Config: ClassVar[type[BaseModel] | None] = None
    # When True, the engine consults the EngineHooks node cache for this node (load/store by fingerprint).
    CACHED: ClassVar[bool] = False

    def __init__(self, node_id: str) -> None:
        """
        Args:
            node_id (str): The node's id, unique among its siblings (the transition endpoints).
        """
        LoggerClass.__init__(self)
        self.id = node_id

    def describe(self) -> NodeSchema:
        """
        Emit the self-describing schema of this node (a group adds its children + transitions).

        Returns:
            NodeSchema: id + kind + the node's config JSON schema.
        """
        config_schema = self.Config.model_json_schema() if self.Config is not None else None
        return NodeSchema(id=self.id, kind=self.KIND, config_schema=config_schema)


class ActionNode(Node):
    """A leaf node — one elementary unit of work. Concrete actions implement ``execute``."""

    KIND = NodeKind.ACTION

    @abstractmethod
    async def execute(self, ctx: Context) -> NodeOutput:
        """
        Perform the action and return its typed output.

        Args:
            ctx (Context): The resolved typed input (``ctx.input``) + the injected services
                (``ctx.service("...")``).

        Returns:
            NodeOutput: The node's output (may carry a ``score`` consumed by a ``score_below`` edge).
        """
        ...


class GroupNode(Node):
    """
    A node containing child nodes wired by transitions; its control shape emerges from the edges.

    All-``always`` edges -> a sequence; ``score_below`` edges -> an escalation; ``on_failure`` edges ->
    a fallback. The flow starts at ``entry`` and follows the first firing outgoing edge of each node
    until a node has no firing edge (the terminal). ``assemble`` turns the children's outputs into the
    group's typed Output.
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

    def assemble(self, outputs: dict[str, NodeOutput], terminal: NodeOutput) -> NodeOutput:
        """
        Turn the children's outputs into the group's typed Output.

        Default: the terminal node's output IS the group output (the natural shape for an escalation,
        where every candidate shares the group's Output type). A sequence group that must combine
        several children overrides this to build its Output from ``outputs``.

        Args:
            outputs (dict[str, NodeOutput]): Every child output collected during the flow, by node id.
            terminal (NodeOutput): The output of the node where the flow terminated.

        Returns:
            NodeOutput: The group's output.
        """
        return terminal

    def describe(self) -> NodeSchema:
        """
        Emit the group's schema: its own identity/config plus its children and the wiring transitions.

        Returns:
            NodeSchema: id + kind + config + child schemas + the transitions (edges + conditions).
        """
        # 1. Start from the base node schema, then add the graph (children + edges).
        schema = super().describe()
        schema.nodes = [child.describe() for child in self.nodes]
        schema.transitions = [
            TransitionSchema(source=t.source, target=t.target, when=t.when, threshold=t.threshold)
            for t in self.transitions
        ]
        return schema


__all__ = ["Node", "ActionNode", "GroupNode"]

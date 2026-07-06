# ====== Code Summary ======
# A Group node — a sub-graph of child nodes wired together by transitions.
#
# A Group is itself a node (NODE_TYPE = GROUP), so groups nest inside groups and a whole pipeline
# is just the outermost Group. It holds the full graph wiring as instance data — the children, the
# transitions between them (control flow), and the bindings that feed each child's input (data
# flow) — the declarative structure that gets serialised into the pipeline blob. Sequence,
# escalation and fallback all emerge from the transitions (see transition.py); the Group adds no
# control logic of its own — the engine walks it.
#
# NOTE: describe() returns the generic GROUP type-card (the palette entry). The recursive
# description of a BUILT pipeline (walking a group's actual children) is the explorer's job and
# is built with the engine, not here.

# ====== Local Project Imports ======
from .describe import NodeDescription
from .enums import NodeType
from .io import Binding
from .node import AbstractNode
from .transition import Transition


class Group(AbstractNode):
    """
    A sub-graph of child nodes connected by transitions.

    The children and transitions are the declarative graph structure (the serialised blob); the
    Group itself carries no execution logic. Because a Group is an AbstractNode, it nests inside
    other groups, and a whole pipeline is simply the outermost Group.
    """

    KIND = "group"
    NODE_TYPE = NodeType.GROUP
    NAME = "Group"
    SUMMARY = "A sub-graph of nodes wired together by transitions."

    def __init__(
        self,
        id: str,
        children: list[AbstractNode],
        transitions: list[Transition] | None = None,
        bindings: dict[str, dict[str, Binding]] | None = None,
    ) -> None:
        """
        Args:
            id (str): Graph-unique identifier this group is wired under.
            children (list[AbstractNode]): The nodes contained in this group (may be groups).
            transitions (list[Transition] | None): Control-flow edges between the children.
            bindings (dict[str, dict[str, Binding]] | None): Data wiring, keyed by child id then by
                that child's input-slot name → the Binding that fills it. Defaults to none.
        """
        super().__init__(id)
        # 1. Store the declarative structure: children + control flow + data wiring.
        self.children = children
        self.transitions = transitions or []
        self.bindings = bindings or {}
        # 2. Fail fast on duplicate child ids — transitions and bindings address children by id.
        self.__check_unique_child_ids()

    def __check_unique_child_ids(self) -> None:
        """Reject duplicate child identifiers, which would make transitions ambiguous."""
        seen: set[str] = set()
        duplicates: set[str] = set()
        for child in self.children:
            if child.id in seen:
                duplicates.add(child.id)
            seen.add(child.id)
        if duplicates:
            raise ValueError(
                f"Group '{self.id}' has duplicate child ids: {', '.join(sorted(duplicates))}"
            )

    @classmethod
    def describe(cls) -> NodeDescription:
        """
        Return the generic GROUP type-card (palette entry).

        Returns:
            NodeDescription: The group's type metadata. A built group's children are described
                by the explorer, not here.
        """
        return NodeDescription(
            kind=cls.KIND,
            node_type=cls.NODE_TYPE,
            name=cls.NAME,
            summary=cls.SUMMARY,
            error_policy=cls.ERROR_POLICY,
        )


__all__ = ["Group"]

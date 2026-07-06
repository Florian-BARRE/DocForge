# ====== Code Summary ======
# A ForEach node — a sub-graph run once PER ITEM of a list, results collected in order.
#
# It is the per-item counterpart of Group: `over` binds the list to iterate (any upstream list
# field), `item_field` names how each item is exposed to the body's group input, and the body is a
# plain Group — so per-item escalation (ScoreBelow), value routing (WhenEquals) and recovery are
# ordinary transitions inside it. The COLLECTION CONTRACT: every terminal of the body produces the
# SAME single-slot artefact (validated at creation), and the ForEach emits ForEachItems with those
# values in item order — a typed list the rest of the graph consumes like any other output field.

# ====== Internal Project Imports ======
from shared_libs.public_models import Artifact

# ====== Local Project Imports ======
from .describe import NodeDescription
from .enums import NodeType
from .graph import GraphTopology
from .group import Group
from .io import Binding, NodeOutput
from .node import AbstractNode, ActionNode
from .slots import SlotTypes


class ForEachItems(NodeOutput):
    """The collected output of a ForEach — one entry per item, in item order."""

    items: list[Artifact]


class ForEach(AbstractNode):
    """
    A sub-graph executed once per item of a bound list.

    Declarative like Group: it carries the loop wiring (over / item_field / body), no execution
    logic — the engine walks it. NOTE: the body's node INSTANCES are shared across concurrent
    item runs — a node must never mutate instance state in run() (config is read-only by design).
    """

    KIND = "foreach"
    NODE_TYPE = NodeType.FOREACH
    NAME = "For each"
    SUMMARY = "Run a sub-graph once per item of a list, collecting the results in order."

    def __init__(
        self,
        id: str,
        body: Group,
        over: Binding,
        item_field: str,
        max_concurrency: int = 4,
    ) -> None:
        """
        Args:
            id (str): Graph-unique identifier this node is wired under.
            body (Group): The sub-graph run once per item.
            over (Binding): Where the iterated list comes from (a ``list[...]`` field upstream).
            item_field (str): Group-input field name each item is exposed under to the body
                (its children read it via ``FromGroupInput(item_field)``).
            max_concurrency (int): How many items may run their body at the same time.
        """
        super().__init__(id)
        # 1. A non-positive concurrency would deadlock the semaphore — fail at construction,
        #    mirroring the blob's ge=1 (this guards the programmatic construction path).
        if max_concurrency < 1:
            raise ValueError(
                f"ForEach '{id}' max_concurrency must be >= 1, got {max_concurrency}"
            )
        # 2. Store the declarative loop structure.
        self.body = body
        self.over = over
        self.item_field = item_field
        self.max_concurrency = max_concurrency

    @classmethod
    def describe(cls) -> NodeDescription:
        """
        Return the generic FOREACH type-card (palette entry).

        Returns:
            NodeDescription: The node's type metadata. A built ForEach's body is described by
                the explorer, not here.
        """
        return NodeDescription(
            kind=cls.KIND,
            node_type=cls.NODE_TYPE,
            name=cls.NAME,
            summary=cls.SUMMARY,
            error_policy=cls.ERROR_POLICY,
        )

    def item_type(self) -> type | None:
        """
        The body's uniform terminal artefact — what each item collects into ``items``.

        Returns:
            type | None: The single artefact class every terminal of the body produces, or None
            when the body does not honour the collection contract (the validator reports why).
        """
        # 1. The static terminals: children with no outgoing transition.
        child_ids = {child.id for child in self.body.children}
        exit_ids = GraphTopology.exits(child_ids, self.body.transitions)
        if not exit_ids:
            return None

        # 2. Every terminal must be an action node producing exactly ONE Artifact-class slot —
        #    scalar slots (str, int…) are not collectable into ForEachItems.items: list[Artifact].
        terminal_types: set[type] = set()
        by_id = {child.id: child for child in self.body.children}
        for exit_id in exit_ids:
            terminal = by_id[exit_id]
            if not isinstance(terminal, ActionNode):
                return None
            fields = terminal.Produces.model_fields
            if len(fields) != 1:
                return None
            element, is_list = SlotTypes.element(next(iter(fields.values())).annotation)
            if element is None or is_list or not issubclass(element, Artifact):
                return None
            terminal_types.add(element)

        # 3. Uniformity: one artefact class across every terminal.
        return terminal_types.pop() if len(terminal_types) == 1 else None


__all__ = ["ForEach", "ForEachItems"]

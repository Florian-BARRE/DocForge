# ====== Code Summary ======
# The graph validator — the creation-time guard that refuses an incoherent pipeline before it is
# stored or run. For every group (recursively) it computes the shared per-group context (children,
# valid transitions, cycle flag, ancestors) and checks: exactly one entry node, no transition cycle,
# transitions/bindings referencing existing nodes. It then delegates the independent rule groups —
# per-child bindings, transition routing, whole-graph uniqueness — to the rules/ sub-package. It
# collects ALL issues (never stops at the first) so the whole set can be surfaced at once.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    ForEach,
    GraphTopology,
    Group,
    Transition,
)

# ====== Local Project Imports ======
from .issues import GraphInvalidError, ValidationCode, ValidationIssue
from .rules import (
    ChildBindingRules,
    IssueCollector,
    RoutingRules,
    UniquenessRules,
)


class GraphValidator(LoggerClass):
    """
    Validates a built pipeline Group at creation time, collecting every issue found.

    Stateless across calls. Operates on live node instances so it can read each node's Consumes /
    Produces types for the binding and type-compatibility checks.

    Owns the group walk and the per-group context (children, valid transitions, cycle flag,
    ancestors) computed once, then delegates the independent checks — bindings, routing, uniqueness —
    to the rules/ sub-package, threading a single IssueCollector so recorded order is preserved.
    """

    def __init__(self) -> None:
        LoggerClass.__init__(self)

    def __validate_group(self, group: Group, collector: IssueCollector) -> None:
        """Validate one group and recurse into its sub-groups."""
        location = f"group '{group.id}'"
        children = {child.id: child for child in group.children}
        child_ids = set(children)

        # 1. Transitions must reference existing children; keep the valid ones for the graph checks.
        valid_transitions: list[Transition] = []
        for transition in group.transitions:
            if transition.from_node_id in child_ids and transition.to_node_id in child_ids:
                valid_transitions.append(transition)
            else:
                collector.record(
                    ValidationCode.UNKNOWN_NODE,
                    location,
                    f"transition '{transition.from_node_id}' -> '{transition.to_node_id}' "
                    f"references an unknown node",
                )

        # 2. Exactly one entry node — an EMPTY group is a defect too (a stored pipeline
        #    with zero nodes would silently run nothing; caught by the UI agent's probing).
        if not group.children:
            collector.record(
                ValidationCode.NO_SINGLE_ENTRY,
                location,
                f"group has no nodes — a pipeline must contain at least one",
            )
        else:
            entries = GraphTopology.entries(child_ids, valid_transitions)
            if len(entries) != 1:
                collector.record(
                    ValidationCode.NO_SINGLE_ENTRY,
                    location,
                    f"must have exactly one entry node, found {len(entries)}",
                )

        # 3. No cycle; ancestors (for the upstream check) only make sense when acyclic.
        has_cycle = GraphTopology.has_cycle(child_ids, valid_transitions)
        if has_cycle:
            collector.record(ValidationCode.CYCLE, location, "the transitions form a cycle")
        ancestors = {} if has_cycle else GraphTopology.ancestors(child_ids, valid_transitions)

        # 4. Binding maps must reference existing children.
        for node_id in group.bindings:
            if node_id not in child_ids:
                collector.record(
                    ValidationCode.UNKNOWN_NODE,
                    location,
                    f"bindings reference an unknown node '{node_id}'",
                )

        # 5. Per-child binding + slot checks.
        for child in group.children:
            ChildBindingRules.validate_child(
                group, child, children, ancestors, has_cycle, collector
            )

        # 6-7. Condition-producer coherence, then single-path routing / switch exhaustiveness.
        RoutingRules.check(location, children, valid_transitions, collector)

        # 8. Recurse into sub-graphs: plain groups, and foreach bodies (which must also honour the
        #    collection contract — uniform single-slot terminals — so their items are typed).
        for child in group.children:
            if isinstance(child, Group):
                self.__validate_group(child, collector)
            elif isinstance(child, ForEach):
                self.__validate_group(child.body, collector)
                if child.item_type() is None:
                    collector.record(
                        ValidationCode.FOREACH_INVALID_BODY,
                        f"group '{group.id}' / foreach '{child.id}'",
                        "every terminal of the body must be an action node producing the same "
                        "single-slot Artifact (the collection contract; scalar slots are not "
                        "collectable)",
                    )

    def validate(self, group: Group) -> list[ValidationIssue]:
        """
        Validate a built pipeline graph and return every issue found.

        Args:
            group (Group): The graph root to validate.

        Returns:
            list[ValidationIssue]: All issues (empty if the graph is valid).
        """
        collector = IssueCollector()
        self.__validate_group(group, collector)
        UniquenessRules.check(group, collector)
        return collector.issues

    def validate_or_raise(self, group: Group) -> None:
        """
        Validate a graph and raise if it is invalid.

        Args:
            group (Group): The graph root to validate.

        Raises:
            GraphInvalidError: If any issue is found, carrying the full list.
        """
        issues = self.validate(group)
        if issues:
            self.logger.error(
                f"Pipeline '{group.id}' failed validation with {len(issues)} issue(s)"
            )
            raise GraphInvalidError(issues)
        self.logger.info(f"Pipeline '{group.id}' validated: no issues")


__all__ = ["GraphValidator"]

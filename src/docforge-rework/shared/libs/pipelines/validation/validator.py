# ====== Code Summary ======
# The graph validator — the creation-time guard that refuses an incoherent pipeline before it is
# stored or run. For every group (recursively) it checks: exactly one entry node, no transition
# cycle, transitions/bindings referencing existing nodes, every action node's CONSUMES slot bound,
# each FromNode binding pointing UPSTREAM at an existing producer field whose type is compatible
# with the consuming slot, and ScoreBelow edges only from a ScoredOutput producer. It collects ALL
# issues (never stops at the first) so the whole set can be surfaced at once.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    AbstractNode,
    ActionNode,
    ConditionKind,
    ForEach,
    FromFirst,
    FromNode,
    GraphTopology,
    Group,
    ScoreBelow,
    ScoredOutput,
    SlotTypes,
    Transition,
    WhenEquals,
)

# ====== Local Project Imports ======
from .issues import GraphInvalidError, ValidationCode, ValidationIssue


class GraphValidator(LoggerClass):
    """
    Validates a built pipeline Group at creation time, collecting every issue found.

    Stateless across calls. Operates on live node instances so it can read each node's Consumes /
    Produces types for the binding and type-compatibility checks.

    Deliberately a single cohesive class: all checks share the same per-group context (children,
    ancestors, cycle flag) computed once, so keeping them together is clearer than splitting.
    """

    def __init__(self) -> None:
        LoggerClass.__init__(self)

    def __record(
        self,
        issues: list[ValidationIssue],
        code: ValidationCode,
        location: str,
        message: str,
    ) -> None:
        """Log and collect a single issue."""
        self.logger.debug(f"validation issue [{code}] {location}: {message}")
        issues.append(ValidationIssue(code=code, location=location, message=message))

    def __check_from_node(
        self,
        location: str,
        consumer_id: str,
        slot_name: str,
        consumer_type: type | None,
        binding: FromNode,
        children: dict[str, AbstractNode],
        ancestors: dict[str, set[str]],
        has_cycle: bool,
        issues: list[ValidationIssue],
    ) -> None:
        """Validate a single FromNode binding: producer exists, is upstream, field + type match."""
        # 1. The producer must exist in the group.
        producer = children.get(binding.node_id)
        if producer is None:
            self.__record(
                issues,
                ValidationCode.UNKNOWN_NODE,
                location,
                f"slot '{slot_name}' binds to unknown node '{binding.node_id}'",
            )
            return

        # 2. The producer must be upstream (skip when cyclic — the order is undefined).
        if not has_cycle and binding.node_id not in ancestors.get(consumer_id, set()):
            self.__record(
                issues,
                ValidationCode.BINDING_NOT_UPSTREAM,
                location,
                f"slot '{slot_name}' binds to '{binding.node_id}', which is not upstream of it",
            )

        # 3. A foreach producer exposes exactly one field: 'items', typed by its body's terminals.
        if isinstance(producer, ForEach):
            self.__check_foreach_field(
                location, slot_name, consumer_type, binding, producer, issues
            )
            return

        # 4. Field + type checks apply only to action producers (a group has no typed Produces).
        if not isinstance(producer, ActionNode):
            return
        produces_fields = producer.Produces.model_fields
        if binding.field_name not in produces_fields:
            self.__record(
                issues,
                ValidationCode.UNKNOWN_FIELD,
                location,
                f"producer '{binding.node_id}' has no output field '{binding.field_name}'",
            )
            return
        if consumer_type is None:
            return
        producer_type = produces_fields[binding.field_name].annotation
        # Shape-aware compatibility: plain↔plain and list↔list (by element subclass); a shape
        # mismatch (a list into a single slot, or the reverse) is always an error.
        producer_element, producer_is_list = SlotTypes.element(producer_type)
        consumer_element, consumer_is_list = SlotTypes.element(consumer_type)
        if producer_element is None or consumer_element is None:
            return  # an unreadable annotation cannot be judged here (enforced at definition)
        if producer_is_list != consumer_is_list or not issubclass(
            producer_element, consumer_element
        ):
            self.__record(
                issues,
                ValidationCode.TYPE_MISMATCH,
                location,
                f"slot '{slot_name}' expects '{SlotTypes.label(consumer_type)}' but "
                f"'{binding.node_id}.{binding.field_name}' produces "
                f"'{SlotTypes.label(producer_type)}'",
            )

    def __check_foreach_field(
        self,
        location: str,
        slot_name: str,
        consumer_type: type | None,
        binding: FromNode,
        producer: ForEach,
        issues: list[ValidationIssue],
    ) -> None:
        """Validate a binding that reads a foreach's output: the field and the collected type."""
        # 1. The only output field a foreach exposes is the collected 'items'.
        if binding.field_name != "items":
            self.__record(
                issues,
                ValidationCode.UNKNOWN_FIELD,
                location,
                f"foreach '{binding.node_id}' only outputs 'items', not '{binding.field_name}'",
            )
            return
        # 2. Type check: the consumer must take a list of the body's terminal artefact. A broken
        #    body (item_type None) is reported by the foreach's own body check, not here.
        item_type = producer.item_type()
        if consumer_type is None or item_type is None:
            return
        consumer_element, consumer_is_list = SlotTypes.element(consumer_type)
        if consumer_element is None:
            return
        if not consumer_is_list or not issubclass(item_type, consumer_element):
            self.__record(
                issues,
                ValidationCode.TYPE_MISMATCH,
                location,
                f"slot '{slot_name}' expects '{SlotTypes.label(consumer_type)}' but foreach "
                f"'{binding.node_id}' produces 'list[{item_type.__name__}]'",
            )

    def __check_foreach_over(
        self,
        location: str,
        child: ForEach,
        children: dict[str, AbstractNode],
        ancestors: dict[str, set[str]],
        has_cycle: bool,
        issues: list[ValidationIssue],
    ) -> None:
        """Validate a foreach's 'over' binding: standard FromNode checks plus the list shape."""
        if not isinstance(child.over, FromNode):
            return  # run/group inputs are dynamic — checked at run time
        # 1. Producer exists, is upstream, field exists (the standard binding checks).
        self.__check_from_node(
            location, child.id, "over", None, child.over, children, ancestors, has_cycle, issues
        )
        # 2. The bound field must be a list — the loop needs something to iterate.
        producer = children.get(child.over.node_id)
        if not isinstance(producer, ActionNode):
            return
        field_info = producer.Produces.model_fields.get(child.over.field_name)
        if field_info is None:
            return  # already reported as unknown_field above
        element, is_list = SlotTypes.element(field_info.annotation)
        if element is not None and not is_list:
            self.__record(
                issues,
                ValidationCode.TYPE_MISMATCH,
                location,
                f"'over' must bind a list field, but '{child.over.node_id}."
                f"{child.over.field_name}' produces '{SlotTypes.label(field_info.annotation)}'",
            )

    def __validate_child(
        self,
        group: Group,
        child: AbstractNode,
        children: dict[str, AbstractNode],
        ancestors: dict[str, set[str]],
        has_cycle: bool,
        issues: list[ValidationIssue],
    ) -> None:
        """Validate one child's bindings — full slot coverage for action nodes, FromNode for groups."""
        location = f"group '{group.id}' / node '{child.id}'"
        node_bindings = group.bindings.get(child.id, {})

        # 0. ForEach child: its single input is the inline 'over' binding.
        if isinstance(child, ForEach):
            self.__check_foreach_over(location, child, children, ancestors, has_cycle, issues)
            return

        # 1. Action node: every declared CONSUMES slot must be bound; a FromFirst join is checked
        #    candidate by candidate (each one like a plain FromNode).
        if isinstance(child, ActionNode):
            for slot_name, field_info in child.Consumes.model_fields.items():
                binding = node_bindings.get(slot_name)
                if binding is None:
                    # An optional slot (field with a default) may stay unbound — mirror of
                    # the resolver's rule, so validation and execution always agree.
                    if field_info.is_required():
                        self.__record(
                            issues,
                            ValidationCode.MISSING_BINDING,
                            location,
                            f"required input slot '{slot_name}' has no binding",
                        )
                    continue
                if isinstance(binding, FromNode):
                    self.__check_from_node(
                        location,
                        child.id,
                        slot_name,
                        field_info.annotation,
                        binding,
                        children,
                        ancestors,
                        has_cycle,
                        issues,
                    )
                elif isinstance(binding, FromFirst):
                    for candidate in binding.candidates:
                        self.__check_from_node(
                            location,
                            child.id,
                            slot_name,
                            field_info.annotation,
                            candidate,
                            children,
                            ancestors,
                            has_cycle,
                            issues,
                        )
            return

        # 2. Group child: input is a dynamic dict, so only its FromNode bindings can be checked
        #    (upstream + producer field), without a consuming slot type.
        for field_name, binding in node_bindings.items():
            if isinstance(binding, FromNode):
                self.__check_from_node(
                    location,
                    child.id,
                    field_name,
                    None,
                    binding,
                    children,
                    ancestors,
                    has_cycle,
                    issues,
                )
            elif isinstance(binding, FromFirst):
                for candidate in binding.candidates:
                    self.__check_from_node(
                        location,
                        child.id,
                        field_name,
                        None,
                        candidate,
                        children,
                        ancestors,
                        has_cycle,
                        issues,
                    )

    def __validate_group(self, group: Group, issues: list[ValidationIssue]) -> None:
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
                self.__record(
                    issues,
                    ValidationCode.UNKNOWN_NODE,
                    location,
                    f"transition '{transition.from_node_id}' -> '{transition.to_node_id}' "
                    f"references an unknown node",
                )

        # 2. Exactly one entry node — an EMPTY group is a defect too (a stored pipeline
        #    with zero nodes would silently run nothing; caught by the UI agent's probing).
        if not group.children:
            self.__record(
                issues,
                ValidationCode.NO_SINGLE_ENTRY,
                location,
                f"group has no nodes — a pipeline must contain at least one",
            )
        else:
            entries = GraphTopology.entries(child_ids, valid_transitions)
            if len(entries) != 1:
                self.__record(
                    issues,
                    ValidationCode.NO_SINGLE_ENTRY,
                    location,
                    f"must have exactly one entry node, found {len(entries)}",
                )

        # 3. No cycle; ancestors (for the upstream check) only make sense when acyclic.
        has_cycle = GraphTopology.has_cycle(child_ids, valid_transitions)
        if has_cycle:
            self.__record(issues, ValidationCode.CYCLE, location, "the transitions form a cycle")
        ancestors = {} if has_cycle else GraphTopology.ancestors(child_ids, valid_transitions)

        # 4. Binding maps must reference existing children.
        for node_id in group.bindings:
            if node_id not in child_ids:
                self.__record(
                    issues,
                    ValidationCode.UNKNOWN_NODE,
                    location,
                    f"bindings reference an unknown node '{node_id}'",
                )

        # 5. Per-child binding + slot checks.
        for child in group.children:
            self.__validate_child(group, child, children, ancestors, has_cycle, issues)

        # 6. Condition-specific producer checks: a ScoreBelow edge needs a ScoredOutput producer;
        #    a WhenEquals edge needs the routed field to exist on the producer's Produces.
        for transition in valid_transitions:
            producer = children[transition.from_node_id]
            if isinstance(transition.condition, ScoreBelow):
                if not (
                    isinstance(producer, ActionNode) and issubclass(producer.Produces, ScoredOutput)
                ):
                    self.__record(
                        issues,
                        ValidationCode.SCORE_BELOW_NOT_SCORED,
                        location,
                        f"ScoreBelow edge from '{transition.from_node_id}' whose output is not a ScoredOutput",
                    )
            elif isinstance(transition.condition, WhenEquals):
                if isinstance(producer, ActionNode) and (
                    transition.condition.field not in producer.Produces.model_fields
                ):
                    self.__record(
                        issues,
                        ValidationCode.WHEN_EQUALS_UNKNOWN_FIELD,
                        location,
                        f"WhenEquals edge from '{transition.from_node_id}' routes on field "
                        f"'{transition.condition.field}', which its output does not have",
                    )

        # 7. Single-path routing: at most one outgoing transition per condition kind per node —
        #    EXCEPT WhenEquals, the switch: several are allowed when they share the SAME field and
        #    carry DISTINCT values (mutually exclusive branches). Anything else is ambiguous.
        outgoing: dict[str, list[Transition]] = {}
        for transition in valid_transitions:
            outgoing.setdefault(transition.from_node_id, []).append(transition)
        for node_id, transitions in outgoing.items():
            kinds = [t.condition.kind for t in transitions]
            for kind in set(kinds):
                if kinds.count(kind) <= 1:
                    continue
                if kind == ConditionKind.WHEN_EQUALS:
                    switches = [
                        t.condition for t in transitions if isinstance(t.condition, WhenEquals)
                    ]
                    fields = {condition.field for condition in switches}
                    values = [condition.equals for condition in switches]
                    if len(fields) > 1:
                        self.__record(
                            issues,
                            ValidationCode.AMBIGUOUS_ROUTING,
                            location,
                            f"node '{node_id}' has WhenEquals transitions on different fields "
                            f"({sorted(fields)}) — a switch must route on a single field",
                        )
                    if len(values) != len(set(values)):
                        self.__record(
                            issues,
                            ValidationCode.AMBIGUOUS_ROUTING,
                            location,
                            f"node '{node_id}' has duplicate WhenEquals values — branches must be "
                            f"mutually exclusive",
                        )
                else:
                    self.__record(
                        issues,
                        ValidationCode.AMBIGUOUS_ROUTING,
                        location,
                        f"node '{node_id}' has {kinds.count(kind)} outgoing '{kind}' transitions "
                        f"(routing is ambiguous; fan-out is not supported)",
                    )

        # 8. Recurse into sub-graphs: plain groups, and foreach bodies (which must also honour the
        #    collection contract — uniform single-slot terminals — so their items are typed).
        for child in group.children:
            if isinstance(child, Group):
                self.__validate_group(child, issues)
            elif isinstance(child, ForEach):
                self.__validate_group(child.body, issues)
                if child.item_type() is None:
                    self.__record(
                        issues,
                        ValidationCode.FOREACH_INVALID_BODY,
                        f"group '{group.id}' / foreach '{child.id}'",
                        "every terminal of the body must be an action node producing the same "
                        "single-slot Artifact (the collection contract; scalar slots are not "
                        "collectable)",
                    )

    def __check_unique_nodes(self, root: Group, issues: list[ValidationIssue]) -> None:
        """Reject any UNIQUE_IN_GRAPH kind appearing more than once in the WHOLE graph."""
        # 1. Walk the full tree (nested groups and foreach bodies included), counting per kind.
        occurrences: dict[str, list[str]] = {}

        def walk(group: Group) -> None:
            for child in group.children:
                if isinstance(child, ActionNode) and child.UNIQUE_IN_GRAPH:
                    occurrences.setdefault(child.KIND, []).append(child.id)
                elif isinstance(child, Group):
                    walk(child)
                elif isinstance(child, ForEach):
                    walk(child.body)

        walk(root)

        # 2. One issue per duplicated kind, naming every instance so the UI can badge them all.
        for kind, ids in occurrences.items():
            if len(ids) > 1:
                self.__record(
                    issues,
                    ValidationCode.DUPLICATE_UNIQUE_NODE,
                    f"group '{root.id}'",
                    f"node kind '{kind}' is single-use but appears {len(ids)} times "
                    f"({', '.join(ids)})",
                )

    def validate(self, group: Group) -> list[ValidationIssue]:
        """
        Validate a built pipeline graph and return every issue found.

        Args:
            group (Group): The graph root to validate.

        Returns:
            list[ValidationIssue]: All issues (empty if the graph is valid).
        """
        issues: list[ValidationIssue] = []
        self.__validate_group(group, issues)
        self.__check_unique_nodes(group, issues)
        return issues

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

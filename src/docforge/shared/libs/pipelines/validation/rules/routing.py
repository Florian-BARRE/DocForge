# ====== Code Summary ======
# The routing rules over a group's transitions: (1) condition-producer coherence — a ScoreBelow edge
# needs a ScoredOutput producer, a WhenEquals edge needs the routed field on the producer — and (2)
# single-path routing — at most one outgoing transition per condition kind per node, EXCEPT the
# WhenEquals switch (several allowed on ONE field with DISTINCT values), with closed switch sets
# required to be exhaustive or carry a success-path default. Run after the binding checks.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    AbstractNode,
    ActionNode,
    ConditionKind,
    ScoreBelow,
    ScoredOutput,
    Transition,
    WhenEquals,
)

# ====== Local Project Imports ======
from ..issues import ValidationCode
from .collector import IssueCollector


class RoutingRules:
    """Static-only checks for a group's transitions: condition/producer coherence and single-path."""

    logger = loggerplusplus.bind(identifier="RoutingRules")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("RoutingRules is a static-only class and cannot be instantiated.")

    @classmethod
    def check(
        cls,
        location: str,
        children: dict[str, AbstractNode],
        valid_transitions: list[Transition],
        collector: IssueCollector,
    ) -> None:
        """Run the condition-producer checks, then the single-path routing checks, in that order."""
        cls.__check_condition_producers(location, children, valid_transitions, collector)
        cls.__check_single_path(location, children, valid_transitions, collector)

    @classmethod
    def __check_condition_producers(
        cls,
        location: str,
        children: dict[str, AbstractNode],
        valid_transitions: list[Transition],
        collector: IssueCollector,
    ) -> None:
        """Condition-specific producer checks: ScoreBelow needs a ScoredOutput, WhenEquals a field."""
        for transition in valid_transitions:
            producer = children[transition.from_node_id]
            if isinstance(transition.condition, ScoreBelow):
                if not (
                    isinstance(producer, ActionNode) and issubclass(producer.Produces, ScoredOutput)
                ):
                    collector.record(
                        ValidationCode.SCORE_BELOW_NOT_SCORED,
                        location,
                        f"ScoreBelow edge from '{transition.from_node_id}' whose output is not a ScoredOutput",
                    )
            elif isinstance(transition.condition, WhenEquals):
                if isinstance(producer, ActionNode) and (
                    transition.condition.field not in producer.Produces.model_fields
                ):
                    collector.record(
                        ValidationCode.WHEN_EQUALS_UNKNOWN_FIELD,
                        location,
                        f"WhenEquals edge from '{transition.from_node_id}' routes on field "
                        f"'{transition.condition.field}', which its output does not have",
                    )

    @classmethod
    def __check_single_path(
        cls,
        location: str,
        children: dict[str, AbstractNode],
        valid_transitions: list[Transition],
        collector: IssueCollector,
    ) -> None:
        """Single-path routing: at most one outgoing transition per condition kind per node —
        EXCEPT WhenEquals, the switch: several are allowed when they share the SAME field and
        carry DISTINCT values (mutually exclusive branches). Anything else is ambiguous."""
        outgoing: dict[str, list[Transition]] = {}
        for transition in valid_transitions:
            outgoing.setdefault(transition.from_node_id, []).append(transition)
        for node_id, transitions in outgoing.items():
            kinds = [t.condition.kind for t in transitions]
            for kind in set(kinds):
                if kind == ConditionKind.WHEN_EQUALS:
                    # Validate the switch on ANY number of WhenEquals edges (>= 1), not only 2+. Its
                    # field/value-uniqueness checks are no-ops for a lone edge, but the closed-set
                    # EXHAUSTIVENESS check is not: a single edge on a closed SWITCH_FIELDS field with
                    # no OnSuccess/Always default silently truncates the group as SUCCESS on every
                    # unmatched value at run time — exactly what this check exists to reject.
                    cls.__check_switch(location, node_id, children, transitions, collector)
                elif kinds.count(kind) > 1:
                    collector.record(
                        ValidationCode.AMBIGUOUS_ROUTING,
                        location,
                        f"node '{node_id}' has {kinds.count(kind)} outgoing '{kind}' transitions "
                        f"(routing is ambiguous; fan-out is not supported)",
                    )

    @classmethod
    def __check_switch(
        cls,
        location: str,
        node_id: str,
        children: dict[str, AbstractNode],
        transitions: list[Transition],
        collector: IssueCollector,
    ) -> None:
        """Validate a WhenEquals switch: one field, distinct values, and closed-set exhaustiveness."""
        switches = [t.condition for t in transitions if isinstance(t.condition, WhenEquals)]
        fields = {condition.field for condition in switches}
        values = [condition.equals for condition in switches]
        if len(fields) > 1:
            collector.record(
                ValidationCode.AMBIGUOUS_ROUTING,
                location,
                f"node '{node_id}' has WhenEquals transitions on different fields "
                f"({sorted(fields)}) — a switch must route on a single field",
            )
        if len(values) != len(set(values)):
            collector.record(
                ValidationCode.AMBIGUOUS_ROUTING,
                location,
                f"node '{node_id}' has duplicate WhenEquals values — branches must be "
                f"mutually exclusive",
            )
        # Exhaustiveness: a switch on a field with a CLOSED declared value set (SWITCH_FIELDS) must
        # cover every value OR carry a success-path default (OnSuccess/Always). Otherwise an unmatched
        # value silently falls through and ends the graph as SUCCESS — a truncated result with no error.
        producer = children.get(node_id)
        if len(fields) == 1 and isinstance(producer, ActionNode):
            field = next(iter(fields))
            declared = producer.SWITCH_FIELDS.get(field)
            if declared is not None:
                covered = {str(value) for value in values}
                missing = [value for value in declared if str(value) not in covered]
                has_default = any(
                    transition.condition.kind in (ConditionKind.ON_SUCCESS, ConditionKind.ALWAYS)
                    for transition in transitions
                )
                if missing and not has_default:
                    collector.record(
                        ValidationCode.SWITCH_NOT_EXHAUSTIVE,
                        location,
                        f"node '{node_id}' switches on '{field}' but does not cover "
                        f"{missing} and has no default (OnSuccess/Always) edge — an "
                        f"unmatched value would silently end the graph as success",
                    )


__all__ = ["RoutingRules"]

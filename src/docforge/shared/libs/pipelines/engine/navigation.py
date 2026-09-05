# ====== Code Summary ======
# Graph navigation for the engine: entry-node and child lookup, and — given a source node's outcome —
# the choice of the next node to run. The choice is the MOST SPECIFIC matching outgoing transition,
# so escalation beats routing beats success/failure beats always. This is pure topology plus the
# transition-condition semantics; it holds no run state, so the engine keeps it as a stateless helper.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    AbstractNode,
    Always,
    Condition,
    GraphTopology,
    Group,
    NodeOutput,
    NodeStatus,
    OnFailure,
    OnSuccess,
    ScoreBelow,
    ScoredOutput,
    WhenEquals,
)


class GraphNavigator:
    """Static-only helper: entry lookup, child lookup, and next-node selection by transition."""

    logger = loggerplusplus.bind(identifier="GraphNavigator")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("GraphNavigator is a static-only class and cannot be instantiated.")

    @classmethod
    def entry(cls, group: Group) -> AbstractNode | None:
        """Return the group's entry node — the single child with no incoming transition."""
        # 1. An empty group has nothing to run.
        if not group.children:
            return None
        # 2. Exactly one entry (a child that is never a transition target) is required.
        entries = GraphTopology.entries({child.id for child in group.children}, group.transitions)
        if len(entries) != 1:
            cls.logger.error(
                f"Group '{group.id}' must have exactly one entry node, found {len(entries)}"
            )
            raise ValueError(
                f"Group '{group.id}' must have exactly one entry node, found {len(entries)}."
            )
        return cls.child_by_id(group, entries[0])

    @classmethod
    def child_by_id(cls, group: Group, node_id: str) -> AbstractNode:
        """Return the child node with the given id, or fail loudly."""
        for child in group.children:
            if child.id == node_id:
                return child
        cls.logger.error(f"Group '{group.id}' has no child '{node_id}' referenced by a transition")
        raise ValueError(f"Group '{group.id}' has no child '{node_id}' referenced by a transition.")

    @classmethod
    def next(
        cls, group: Group, node: AbstractNode, status: NodeStatus, output: NodeOutput | None
    ) -> AbstractNode | None:
        """Return the next node to run — the MOST SPECIFIC matching outgoing transition (None = terminal)."""
        outgoing = [t for t in group.transitions if t.from_node_id == node.id]
        outgoing.sort(key=lambda t: cls.__condition_rank(t.condition), reverse=True)
        for transition in outgoing:
            if cls.__condition_matches(transition.condition, status, output):
                return cls.child_by_id(group, transition.to_node_id)
        return None

    @classmethod
    def __condition_matches(
        cls, condition: Condition, status: NodeStatus, output: NodeOutput | None
    ) -> bool:
        """Decide whether a transition's condition holds given the source node's outcome."""
        if isinstance(condition, Always):
            return True
        if isinstance(condition, OnSuccess):
            return status == NodeStatus.SUCCESS
        if isinstance(condition, OnFailure):
            return status == NodeStatus.FAILED
        if isinstance(condition, ScoreBelow):
            # Only a ScoredOutput can be score-gated; a plain output cannot fire this edge.
            if not isinstance(output, ScoredOutput):
                # A FAILED node legitimately has no score, so this edge simply does not apply — no
                # warning. Warn ONLY on a SUCCESS that produced a non-scored output: that is a real
                # wiring mismatch (the build validator requires a ScoreBelow producer to be scored).
                if status == NodeStatus.SUCCESS:
                    cls.logger.warning(
                        f"ScoreBelow transition skipped: output is not a ScoredOutput"
                    )
                return False
            return output.score < condition.threshold
        if isinstance(condition, WhenEquals):
            # Value routing only applies to a SUCCESSFUL output carrying the field.
            if status != NodeStatus.SUCCESS or output is None:
                return False
            if not hasattr(output, condition.field):
                cls.logger.warning(
                    f"WhenEquals transition skipped: output has no field '{condition.field}'"
                )
                return False
            return str(getattr(output, condition.field)) == condition.equals
        return False

    @classmethod
    def __condition_rank(cls, condition: Condition) -> int:
        """Specificity of a condition — the engine checks higher first so a specific edge beats a
        generic one when several would match. ScoreBelow outranks WhenEquals: when quality is bad
        the graph escalates before it routes by value."""
        if isinstance(condition, ScoreBelow):
            return 4
        if isinstance(condition, WhenEquals):
            return 3
        if isinstance(condition, (OnSuccess, OnFailure)):
            return 2
        return 1  # Always


__all__ = ["GraphNavigator"]

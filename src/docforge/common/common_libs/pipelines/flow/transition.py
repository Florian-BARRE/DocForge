# ====== Code Summary ======
# Transition — a directed edge ``source -> target`` between two sibling nodes of a group, carrying a
# fixed Condition that decides whether the edge fires given the source node's result. Transitions are
# the SINGLE control mechanism: a group of nodes wired by ``always`` edges is a sequence; a group wired
# by ``score_below`` edges is an escalation (the old "chain"); ``on_failure`` edges are fallbacks. The
# edge also implies the data wiring — an ``always`` edge feeds the source's output to the target, while
# a conditional edge hands the target the SAME input (the target is an alternative, not a successor).

# ====== Standard Library Imports ======
from dataclasses import dataclass
from typing import Any

# ====== Local Project Imports ======
from .enums import Condition


def _score(output: Any) -> float:
    """Read a result's quality score for a ``score_below`` edge (1.0 when the node exposes none)."""
    return float(getattr(output, "score", 1.0))


@dataclass(frozen=True, slots=True)
class Transition:
    """
    A conditional directed edge between two sibling nodes of a group.

    Attributes:
        source (str): The id of the node the edge leaves.
        target (str): The id of the node the edge enters.
        when (Condition): The condition that fires the edge (default ``always`` = sequential).
        threshold (float): The score threshold, used only by the ``score_below`` condition.
    """

    source: str
    target: str
    when: Condition = Condition.ALWAYS
    threshold: float = 0.0

    def fires(self, output: Any, failed: bool) -> bool:
        """
        Decide whether this edge fires given the source node's result.

        Args:
            output (Any): The source node's output (None when it failed).
            failed (bool): Whether the source node failed.

        Returns:
            bool: True when control should follow this edge to ``target``.
        """
        # 1. Dispatch on the fixed condition vocabulary.
        if self.when == Condition.ALWAYS:
            return not failed
        if self.when == Condition.ON_FAILURE:
            return failed
        if self.when == Condition.SCORE_BELOW:
            # Escalate to the next candidate when this one is not good enough: it FAILED, or it
            # succeeded but its quality score is below the threshold (the chain semantics).
            return failed or _score(output) < self.threshold
        return False


__all__ = ["Transition"]

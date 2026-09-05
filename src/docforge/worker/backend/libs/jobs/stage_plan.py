# ====== Code Summary ======
# StagePlanHelpers — derives the top-level stages a run will ACTUALLY execute on its planned (happy)
# path from a pipeline blob, so the progress denominator counts only nodes that run rather than every
# top-level node. Escalation/fallback steps (reached ONLY via a ScoreBelow or OnFailure edge — e.g. a
# fallback parser that runs only when the primary scores low) never execute on a successful run, so
# counting them in the denominator understates the percentage. This walks the blob's top-level graph
# from its single entry node following only NON-escalation edges to find the stages a good run visits.

# ====== Standard Library Imports ======
from collections import deque
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class StagePlanHelpers:
    """Static-only helper: the planned (happy-path) top-level stage ids of a pipeline blob."""

    logger = loggerplusplus.bind(identifier="StagePlanHelpers")

    # Condition kinds that fire ONLY on a bad outcome — the escalation/fallback edges. A node reached
    # exclusively through these never runs on a successful pass, so it is excluded from the planned
    # set (mirrors transition.ConditionKind.{SCORE_BELOW, ON_FAILURE}).
    _ESCALATION_CONDITIONS = frozenset({"score_below", "on_failure"})

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("StagePlanHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def planned_stage_ids(cls, blob: dict[str, Any]) -> list[str]:
        """
        Return the top-level stage ids reachable from the entry on the planned (happy) path.

        The planned path is the walk from the graph's entry node following every edge EXCEPT the
        escalation/fallback ones (ScoreBelow / OnFailure): those fire only when a node underperforms
        or fails, so their exclusive targets (fallback providers) do not run on a successful pass. A
        node reachable by BOTH a normal and an escalation edge is still included (it is on the happy
        path). Falls back to every top-level node id when the graph has no single clean entry (a
        malformed/edited blob), so the denominator is never smaller than the run really visits.

        Args:
            blob (dict): The normalised pipeline blob (top-level ``nodes`` + ``transitions``).

        Returns:
            list[str]: The planned stage ids, in breadth-first order from the entry.
        """
        # 1. Pull the top-level node ids and transitions (both default-empty for a degenerate blob).
        node_ids = [str(node.get("id", "")) for node in blob.get("nodes", [])]
        transitions = blob.get("transitions", [])
        if not node_ids:
            return []

        # 2. The entry is the single node that is never a transition TARGET (any condition). Without
        #    exactly one, the blob is malformed for this purpose — count every node (never understate).
        targets = {str(t.get("to_node_id", "")) for t in transitions}
        entries = [node_id for node_id in node_ids if node_id not in targets]
        if len(entries) != 1:
            return node_ids

        # 3. Build the adjacency of NON-escalation edges only — each node's happy-path successors.
        happy_edges: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
        for transition in transitions:
            condition = transition.get("condition") or {}
            if condition.get("kind") in cls._ESCALATION_CONDITIONS:
                continue
            src = str(transition.get("from_node_id", ""))
            dst = str(transition.get("to_node_id", ""))
            if src in happy_edges and dst in happy_edges:
                happy_edges[src].append(dst)

        # 4. BFS from the entry over the happy edges — the stages a successful run walks through.
        planned: list[str] = []
        seen: set[str] = set()
        queue: deque[str] = deque([entries[0]])
        while queue:
            node_id = queue.popleft()
            if node_id in seen:
                continue
            seen.add(node_id)
            planned.append(node_id)
            queue.extend(happy_edges.get(node_id, []))
        return planned


__all__ = ["StagePlanHelpers"]

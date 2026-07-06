# ====== Code Summary ======
# Pure graph-topology algorithms over a set of node ids and their transitions: the entry nodes,
# cycle detection, and the ancestor sets. Shared by the engine (entry) and the validator (entry,
# cycle, ancestors). No I/O, no logging — just the algorithms. `has_cycle`/`ancestors` assume every
# transition endpoint is a known id (the validator filters invalid transitions out first).

# ====== Local Project Imports ======
from .transition import Transition


class GraphTopology:
    """Static graph-topology algorithms over a group's child ids and their transitions."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("GraphTopology is a static-only class and cannot be instantiated.")

    @classmethod
    def entries(cls, child_ids: set[str], transitions: list[Transition]) -> list[str]:
        """
        Return the ids that are never a transition target — the entry candidates.

        Args:
            child_ids (set[str]): The group's child ids.
            transitions (list[Transition]): The group's transitions.

        Returns:
            list[str]: Ids with no incoming transition.
        """
        targets = {transition.to_node_id for transition in transitions}
        return [child_id for child_id in child_ids if child_id not in targets]

    @classmethod
    def exits(cls, child_ids: set[str], transitions: list[Transition]) -> list[str]:
        """
        Return the ids that are never a transition source — the terminal candidates.

        Args:
            child_ids (set[str]): The group's child ids.
            transitions (list[Transition]): The group's transitions.

        Returns:
            list[str]: Ids with no outgoing transition.
        """
        sources = {transition.from_node_id for transition in transitions}
        return [child_id for child_id in child_ids if child_id not in sources]

    @classmethod
    def has_cycle(cls, child_ids: set[str], transitions: list[Transition]) -> bool:
        """
        Return whether the transitions form a cycle (Kahn topological sort).

        Args:
            child_ids (set[str]): The group's child ids.
            transitions (list[Transition]): Transitions with known-valid endpoints.

        Returns:
            bool: True if a cycle exists.
        """
        adjacency: dict[str, list[str]] = {child_id: [] for child_id in child_ids}
        in_degree: dict[str, int] = {child_id: 0 for child_id in child_ids}
        for transition in transitions:
            adjacency[transition.from_node_id].append(transition.to_node_id)
            in_degree[transition.to_node_id] += 1

        queue = [child_id for child_id in child_ids if in_degree[child_id] == 0]
        processed = 0
        while queue:
            node_id = queue.pop()
            processed += 1
            for target in adjacency[node_id]:
                in_degree[target] -= 1
                if in_degree[target] == 0:
                    queue.append(target)
        return processed != len(child_ids)

    @classmethod
    def ancestors(cls, child_ids: set[str], transitions: list[Transition]) -> dict[str, set[str]]:
        """
        Map each id to the set of ids that can reach it (its upstream nodes).

        Args:
            child_ids (set[str]): The group's child ids.
            transitions (list[Transition]): Transitions with known-valid endpoints.

        Returns:
            dict[str, set[str]]: Node id → its upstream node ids.
        """
        predecessors: dict[str, list[str]] = {child_id: [] for child_id in child_ids}
        for transition in transitions:
            predecessors[transition.to_node_id].append(transition.from_node_id)

        result: dict[str, set[str]] = {}
        for child_id in child_ids:
            seen: set[str] = set()
            stack = list(predecessors[child_id])
            while stack:
                current = stack.pop()
                if current in seen:
                    continue
                seen.add(current)
                stack.extend(predecessors[current])
            result[child_id] = seen
        return result


__all__ = ["GraphTopology"]

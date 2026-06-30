# ====== Code Summary ======
# FlowEngine — the single generic runner. It executes any node the same way at every level: a leaf
# action runs its ``execute``; a group walks its flow — start at the entry node, run it, follow the
# first firing outgoing transition, and repeat until a node has no firing edge (the terminal, whose
# output is the group's output). The edge kind also wires the data: an ``always`` edge feeds the
# source's output to the target (sequencing), a conditional edge hands the target the SAME input (an
# alternative — so an escalation tries candidates on the same input until one is accepted). Sequence,
# escalation, and fallback all fall out of this one loop, driven purely by the transition conditions.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .node import ActionNode, GroupNode, Node


class FlowEngine(LoggerClass):
    """The generic recursive flow runner — drives actions and groups uniformly."""

    async def run(self, node: Node, data: object) -> object:
        """
        Run a node on its input and return its output.

        Args:
            node (Node): The node to run (an action or a group).
            data (object): The node's input.

        Returns:
            object: The node's output.
        """
        # 1. A leaf does its work; a group walks its internal flow.
        if isinstance(node, ActionNode):
            return await node.execute(data)
        return await self._run_group(node, data)

    async def _run_group(self, group: GroupNode, group_input: object) -> object:
        """
        Walk a group's flow: entry -> first firing edge -> ... -> terminal.

        Args:
            group (GroupNode): The group to run.
            group_input (object): The group's input (fed to the entry + every conditional alternative).

        Returns:
            object: The terminal node's output (the group's output).
        """
        # 1. Start at the entry node with the group input.
        current_id = group.entry
        current_input = group_input
        while True:
            # 2. Run the current node (recurse — a child may itself be a group).
            output = await self.run(group.node(current_id), current_input)

            # 3. Follow the first outgoing edge whose condition fires (declaration order = priority).
            edge = next((t for t in group.outgoing(current_id) if t.fires(output, failed=False)), None)
            if edge is None:
                return output  # terminal -> this node's output is the group's output

            # 4. ``always`` edge -> the target consumes this output (data flows); a conditional edge ->
            #    the target is an alternative and consumes the same group input.
            current_input = output if edge.carries_data() else group_input
            current_id = edge.target


__all__ = ["FlowEngine"]

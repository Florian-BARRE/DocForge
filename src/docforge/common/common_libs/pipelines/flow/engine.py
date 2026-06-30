# ====== Code Summary ======
# FlowEngine — the single generic runner. It executes any node the same way at every level. For each
# node it RESOLVES the typed Input from the node's bindings (the data axis: sibling outputs by id +
# the group input + the run input), then: a leaf action runs its ``execute(ctx)``; a group walks its
# flow — start at the entry node, run it, follow the first firing outgoing transition (the control
# axis), and repeat until a node has no firing edge (the terminal, whose output the group ``assemble``s
# into its own typed Output). Sequence, escalation, and fallback all fall out of this one loop, driven
# purely by the transition conditions; the node bodies stay pure.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .context import Context, RunContext
from .io import NodeInput, NodeOutput
from .node import ActionNode, GroupNode, Node
from .resolver import InputResolver


class FlowEngine(LoggerClass):
    """The generic recursive flow runner — drives actions and groups uniformly."""

    async def run(self, root: Node, run: RunContext) -> NodeOutput:
        """
        Run a node tree from its root and return the root output.

        Args:
            root (Node): The root node (typically the pipeline group).
            run (RunContext): The run-wide handle (run input + injected services).

        Returns:
            NodeOutput: The root node's output.
        """
        # 1. The root's input is resolved against the run input (a pipeline binds from the run input).
        self.logger.info(f"Flow {root.id!r} started.")
        output = await self._run_node(root, run, run.run_input, {})
        self.logger.info(f"Flow {root.id!r} done.")
        return output

    async def _run_node(
        self, node: Node, run: RunContext, group_input: NodeInput, sibling_outputs: dict
    ) -> NodeOutput:
        """
        Resolve a node's typed input, then run it (a leaf executes, a group walks its flow).

        Args:
            node (Node): The node to run.
            run (RunContext): The run-wide handle.
            group_input (NodeInput): The enclosing group's input (source of FromGroupInput).
            sibling_outputs (dict): The outputs of this node's already-run siblings, by node id.

        Returns:
            NodeOutput: The node's output.
        """
        # 1. Resolve the typed Input from this node's bindings (the data axis).
        resolved = InputResolver.resolve(node.Input, run.run_input, group_input, sibling_outputs)

        # 2. A leaf runs its work; a group walks its internal flow with the resolved input as its input.
        if isinstance(node, ActionNode):
            return await node.execute(Context(input=resolved, services=run.services))
        return await self._run_group(node, run, resolved)

    async def _run_group(
        self, group: GroupNode, run: RunContext, group_input: NodeInput
    ) -> NodeOutput:
        """
        Walk a group's flow: entry -> first firing edge -> ... -> terminal, then assemble the output.

        Args:
            group (GroupNode): The group to run.
            run (RunContext): The run-wide handle.
            group_input (NodeInput): The group's resolved input.

        Returns:
            NodeOutput: The group's assembled output.
        """
        # 1. Walk the flow, collecting each child's output by id for downstream bindings.
        outputs: dict[str, NodeOutput] = {}
        current_id = group.entry
        terminal: NodeOutput | None = None
        while True:
            child = group.node(current_id)
            output = await self._run_node(child, run, group_input, outputs)
            outputs[child.id] = output

            # 2. Follow the first outgoing edge whose condition fires (declaration order = priority).
            edge = next(
                (t for t in group.outgoing(current_id) if t.fires(output, failed=False)), None
            )
            if edge is None:
                terminal = output  # no firing edge -> terminal
                break
            current_id = edge.target

        # 3. Assemble the group's typed Output from the collected children (default: the terminal).
        return group.assemble(outputs, terminal)


__all__ = ["FlowEngine"]

# ====== Code Summary ======
# FlowEngine — the single generic runner. Per node it: resolves the typed Input from bindings (data
# axis), runs the gate / node-cache / before+after middleware via the injected EngineHooks, then either
# executes a leaf or walks a group's flow (control axis = transitions). It emits a NodeReport per node
# into a recursive feedback tree, and wraps failures recursively: a group child that fails with no
# fallback edge propagates as a FlowFailure the parent re-wraps (cause chain). Sequence, escalation
# (score_below escalates on low score OR error), and fallback (on_failure) all fall out of one loop;
# the node bodies stay pure — every side effect is a hook.

# ====== Standard Library Imports ======
import time

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .context import Context, RunContext
from .hooks import EngineHooks
from .io import NodeInput, NodeOutput
from .node import ActionNode, GroupNode, Node
from .report import ErrorInfo, FlowFailure, NodeReport, ReportStatus
from .resolver import InputResolver


class FlowEngine(LoggerClass):
    """The generic recursive flow runner — drives actions and groups uniformly, emitting a report tree."""

    def __init__(self, hooks: EngineHooks | None = None) -> None:
        """
        Args:
            hooks (EngineHooks | None): The I/O seam (cache, lifecycle, gates). Defaults to all-no-op.
        """
        LoggerClass.__init__(self)
        self._hooks = hooks or EngineHooks()

    async def run(self, root: Node, run: RunContext) -> tuple[NodeOutput | None, NodeReport]:
        """
        Run a node tree from its root, returning the root output and the feedback tree.

        Args:
            root (Node): The root node (typically the pipeline group).
            run (RunContext): The run-wide handle (run input + injected services).

        Returns:
            tuple[NodeOutput | None, NodeReport]: The root output (None on failure) + the report tree.
        """
        # 1. One-time environment prep, run the root, then the terminal lifecycle.
        self.logger.info(f"Flow {root.id!r} started.")
        await self._hooks.prepare(run)
        output, report = await self._run_node(root, run, run.run_input, {})
        if report.status == ReportStatus.FAILED:
            await self._hooks.mark_failed(run)
            self.logger.error(f"Flow {root.id!r} failed: {report.error}")
        else:
            await self._hooks.mark_done(run)
            self.logger.info(f"Flow {root.id!r} done in {report.duration_ms} ms.")
        return output, report

    async def _run_node(
        self, node: Node, run: RunContext, group_input: NodeInput, sibling_outputs: dict
    ) -> tuple[NodeOutput | None, NodeReport]:
        """
        Run a single node through the middleware, capturing its outcome into a report (never raising).

        Args:
            node (Node): The node to run.
            run (RunContext): The run-wide handle.
            group_input (NodeInput): The enclosing group's input (source of FromGroupInput).
            sibling_outputs (dict): The outputs of this node's already-run siblings, by node id.

        Returns:
            tuple[NodeOutput | None, NodeReport]: The output (None on skip/failure) + the node report.
        """
        report = NodeReport(id=node.id, kind=node.KIND)
        started = time.perf_counter()
        output: NodeOutput | None = None
        try:
            # 1. Resolve the typed input + build the node context.
            resolved = InputResolver.resolve(node.Input, run.run_input, group_input, sibling_outputs)
            ctx = Context(input=resolved, services=run.services)

            # 2. Gate — a vetoed node is skipped (no cache, no run).
            if not await self._hooks.should_run(node, ctx, run):
                report.status = ReportStatus.SKIPPED
                await self._hooks.on_skipped(node, ctx, run)
                return None, report

            # 3. Node cache — a hit short-circuits the node (and its whole subtree).
            if node.CACHED:
                cached = await self._hooks.cache_load(node, ctx, run)
                if cached is not None:
                    report.status = ReportStatus.CACHE_HIT
                    return cached, report

            # 4. Miss — before hook, run the body (leaf execute / group flow), store, after hook.
            await self._hooks.before_node(node, ctx, run)
            if isinstance(node, ActionNode):
                output = await node.execute(ctx)
            else:
                output = await self._run_group(node, run, resolved, report)
            if node.CACHED:
                await self._hooks.cache_store(node, ctx, output, run)
            await self._hooks.after_node(node, ctx, output, run)
            report.status = ReportStatus.OK
        except FlowFailure as failure:
            # A child failed with no fallback: re-wrap its error as this group's cause.
            report.status = ReportStatus.FAILED
            report.error = ErrorInfo(type="FlowFailure", message=str(failure), cause=failure.error_info)
            await self._hooks.on_error(node, failure, run)
        except Exception as exc:
            report.status = ReportStatus.FAILED
            report.error = ErrorInfo.from_exception(exc)
            self.logger.warning(f"Node {node.id!r} raised {type(exc).__name__}: {exc}")
            await self._hooks.on_error(node, exc, run)
        finally:
            report.duration_ms = int((time.perf_counter() - started) * 1000)
        return output, report

    async def _run_group(
        self, group: GroupNode, run: RunContext, group_input: NodeInput, group_report: NodeReport
    ) -> NodeOutput:
        """
        Walk a group's flow: entry -> first firing edge -> ... -> terminal, then assemble the output.

        Args:
            group (GroupNode): The group to run.
            run (RunContext): The run-wide handle.
            group_input (NodeInput): The group's resolved input.
            group_report (NodeReport): The group's report (child reports appended here).

        Returns:
            NodeOutput: The group's assembled output.

        Raises:
            FlowFailure: When a child fails and no outgoing edge fires (no fallback) — propagated to
                the group's own ``_run_node`` so the failure climbs the tree as a recursive cause chain.
        """
        # 1. Walk the flow, collecting each child's output by id for downstream bindings.
        outputs: dict[str, NodeOutput] = {}
        current_id = group.entry
        terminal: NodeOutput | None = None
        while True:
            child = group.node(current_id)
            child_output, child_report = await self._run_node(child, run, group_input, outputs)
            group_report.children.append(child_report)
            failed = child_report.status == ReportStatus.FAILED
            if not failed and child_output is not None:
                outputs[child.id] = child_output

            # 2. Follow the first outgoing edge whose condition fires given the child's result.
            edge = next(
                (t for t in group.outgoing(current_id) if t.fires(child_output, failed=failed)), None
            )
            if edge is None:
                if failed:
                    raise FlowFailure(
                        child_report.error,
                        f"group {group.id!r} failed: node {child.id!r} failed with no fallback edge.",
                    )
                terminal = child_output  # success + no firing edge -> terminal
                break
            current_id = edge.target

        # 3. Assemble the group's typed Output from the collected children (default: the terminal).
        return group.assemble(outputs, terminal)


__all__ = ["FlowEngine"]

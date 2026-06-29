# ====== Code Summary ======
# PipelineEngine — the single generic recursive runner. It drives any node tree the same way at
# every level (a pipeline over its stages == a stage over its steps), so adding a level/stage/step
# never touches this loop. Per node it: pushes the node's local capabilities (vertical axis),
# resolves the required capabilities, resolves the typed Input from sibling outputs + run input
# (horizontal axis), then either (composite) topologically drives its children applying each child's
# error policy, or (leaf) runs it through the cache/gate/hook middleware. Every node yields a
# NodeReport (success or failure) into the feedback tree; the node bodies stay pure — all I/O is
# delegated to the injected EngineHooks.
#
# REFACTOR EXCEPTION (>200 lines): this is one cohesive engine — capability + input resolution, the
# composite topo loop with error-policy dispatch, the leaf cache/gate middleware, and report
# building form a single abstraction that would only fragment if split. The overage is dominated by
# the mandatory contract docstrings.

# ====== Standard Library Imports ======
from __future__ import annotations

import time

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from ..base import (
    AbstractNode,
    CachePolicy,
    CapabilityRegistry,
    CompositeNode,
    ErrorPolicy,
    NodeError,
    NodeOutput,
    PipelineError,
    RunContext,
    Scope,
)

# ====== Local Project Imports ======
from .hooks import EngineHooks
from .report import ErrorInfo, NodeReport, ReportStatus
from .resolver import Resolver


class PipelineEngine(LoggerClass):
    """
    The generic recursive engine that runs any node tree under the common middleware.

    Construct it once with the environment ``EngineHooks`` (no-op by default); call ``run`` per
    document with the root node and a ``RunContext``. The engine owns ALL orchestration; nodes stay
    declarative.
    """

    def __init__(self, hooks: EngineHooks | None = None) -> None:
        """
        Args:
            hooks (EngineHooks | None): The I/O seam (cache, lifecycle, gates). Defaults to all-no-op
                so the engine runs end-to-end with no infrastructure.
        """
        LoggerClass.__init__(self)
        self._hooks = hooks or EngineHooks()

    async def run(
        self, root: AbstractNode, run: "RunContext"
    ) -> tuple[NodeOutput | None, NodeReport]:
        """
        Run a node tree from its root, returning the root output and the feedback tree.

        Args:
            root (AbstractNode): The root node (typically a pipeline).
            run (RunContext): The run-wide state (run input + root capability registry).

        Returns:
            tuple[NodeOutput | None, NodeReport]: The root output (None when the run failed) and the
                hierarchical report.
        """
        # 1. One-time environment prep (e.g. download original bytes).
        await self._hooks.prepare(run)

        # 2. Build the root's input (root has no parent → its parent input IS the run input), then
        # drive it with an empty sibling context.
        root_input = Resolver.build_input(root, run.run_input, run.run_input, {})
        output, report = await self._run_node(
            root, root_input, run.run_input, run.capabilities, run, {}
        )

        # 3. Terminal lifecycle from the root's status.
        if report.status == ReportStatus.FAILED:
            await self._hooks.mark_failed(run)
            self.logger.error(f"Pipeline {root.key!r} failed: {report.error}")
        else:
            await self._hooks.mark_done(run)
            self.logger.info(f"Pipeline {root.key!r} done in {report.duration_ms} ms.")
        return output, report

    async def _run_node(
        self,
        node: AbstractNode,
        node_input: NodeOutput,
        parent_input: NodeOutput,
        registry: "CapabilityRegistry",
        run: "RunContext",
        siblings: dict[str, NodeOutput],
    ) -> tuple[NodeOutput | None, NodeReport]:
        """
        Run a single node (composite or leaf), capturing its outcome into a report (never raising).

        Args:
            node (AbstractNode): The node to run.
            node_input (NodeOutput): The node's already-resolved typed Input.
            parent_input (NodeOutput): The parent composite's resolved input (unused by leaves; this
                node's own input becomes the parent input for ITS children).
            registry (CapabilityRegistry): The capability registry visible at the parent level.
            run (RunContext): The run-wide state.
            siblings (dict[str, NodeOutput]): Outputs of this node's already-run siblings.

        Returns:
            tuple[NodeOutput | None, NodeReport]: The node output (None on failure) and its report.
        """
        _ = parent_input  # reserved for symmetry; a node's own input is what flows to its children
        # 1. Push this node's local capabilities so its subtree can resolve them (vertical axis).
        local = node.local_capabilities()
        scoped_registry = registry.child(local) if local else registry

        report = NodeReport(
            key=node.key,
            kind=str(node.KIND),
            inputs=list(getattr(node_input, "model_fields", {}).keys()),
        )
        started = time.perf_counter()
        output: NodeOutput | None = None
        try:
            # 2. Resolve the capabilities the node declared it requires.
            capabilities = Resolver.resolve_capabilities(node, scoped_registry)

            # 3. Composite -> drive children; leaf -> run the work through the middleware.
            if isinstance(node, CompositeNode):
                output = await self._run_composite(node, node_input, scoped_registry, run, report)
            else:
                output = await self._run_leaf(node, node_input, capabilities, run, report)
            if report.status == ReportStatus.PENDING:
                report.status = ReportStatus.OK
        except PipelineError as exc:
            report.status = ReportStatus.FAILED
            report.error = ErrorInfo.from_exception(exc)
            await self._hooks.on_error(node, exc, run)
        except Exception as exc:  # wrap any non-pipeline exception as a node failure
            wrapped = NodeError(str(exc), node_key=node.key, node_kind=node.KIND, cause=exc)
            report.status = ReportStatus.FAILED
            report.error = ErrorInfo.from_exception(wrapped)
            await self._hooks.on_error(node, wrapped, run)
        finally:
            report.duration_ms = int((time.perf_counter() - started) * 1000)
        return output, report

    async def _run_composite(
        self,
        node: CompositeNode,
        node_input: NodeOutput,
        registry: "CapabilityRegistry",
        run: "RunContext",
        report: NodeReport,
    ) -> NodeOutput | None:
        """
        Topologically drive a composite's children, applying each child's error policy.

        Args:
            node (CompositeNode): The composite node.
            node_input (NodeOutput): The composite's resolved input (the children's parent input).
            registry (CapabilityRegistry): The registry visible to the children.
            run (RunContext): The run-wide state.
            report (NodeReport): The composite's report (children appended here).

        Returns:
            NodeOutput | None: The aggregated output, or None when a FAIL child propagated.
        """
        outputs: dict[str, NodeOutput] = {}
        for child in self._topo_order(node.children):
            # 1. Resolve the child's typed input from sibling outputs + parent input + run input.
            try:
                child_input = Resolver.build_input(child, run.run_input, node_input, outputs)
            except PipelineError as exc:
                child_report = NodeReport(
                    key=child.key, kind=str(child.KIND), status=ReportStatus.FAILED,
                    error=ErrorInfo.from_exception(exc),
                )
                report.add_child(child_report)
                if not self._tolerate(child, child_report, report):
                    return None
                continue

            # 2. Run the child; record its report.
            child_output, child_report = await self._run_node(
                child, child_input, node_input, registry, run, outputs
            )
            report.add_child(child_report)

            # 3. On child failure, apply the child's authoritative error policy.
            if child_report.status == ReportStatus.FAILED:
                if not self._tolerate(child, child_report, report):
                    return None
                continue

            # 4. Success -> publish the child's output for its downstream siblings.
            if child_output is not None:
                outputs[child.key] = child_output

        return node.aggregate(outputs)

    async def _run_leaf(
        self,
        node: AbstractNode,
        node_input: NodeOutput,
        capabilities: object,
        run: "RunContext",
        report: NodeReport,
    ) -> NodeOutput | None:
        """
        Run a leaf node through the gate / cache / hook middleware.

        Args:
            node (AbstractNode): The leaf node.
            node_input (NodeOutput): Its resolved typed Input.
            capabilities (object): Its resolved ``CapabilityView``.
            run (RunContext): The run-wide state.
            report (NodeReport): The leaf's report (status set here for skip/cache).

        Returns:
            NodeOutput | None: The leaf's output, or None when skipped.
        """
        # 1. Gate — a vetoed node is skipped (no cache read, no run).
        if not await self._hooks.should_run(node, run):
            report.status = ReportStatus.SKIPPED
            await self._hooks.on_skipped(node, run)
            return None

        # 2. Node cache — a hit short-circuits the run.
        if getattr(node.SPEC, "cache_policy", None) == CachePolicy.NODE_CACHED:
            cached = await self._hooks.cache_load(node, run)
            if cached is not None:
                report.status = ReportStatus.CACHE_HIT
                return cached

        # 3. Miss — pre-run prep, execute, then store + post-run epilogue.
        await self._hooks.before_node(node, run)
        output = await node.execute(Scope(input=node_input, capabilities=capabilities))
        if getattr(node.SPEC, "cache_policy", None) == CachePolicy.NODE_CACHED:
            await self._hooks.cache_store(node, output, run)
        await self._hooks.after_node(node, output, run)
        return output

    @staticmethod
    def _tolerate(
        child: AbstractNode, child_report: NodeReport, parent_report: NodeReport
    ) -> bool:
        """
        Apply a failed child's error policy: tolerate (continue) or propagate (fail the parent).

        Args:
            child (AbstractNode): The failed child.
            child_report (NodeReport): Its report (its error is copied up on propagation).
            parent_report (NodeReport): The parent report (failed here on propagation).

        Returns:
            bool: True to continue the run (SKIP/DEGRADE); False to fail the parent (FAIL).
        """
        if child.error_policy == ErrorPolicy.FAIL:
            parent_report.status = ReportStatus.FAILED
            parent_report.error = child_report.error
            return False
        # SKIP / DEGRADE — the child stays FAILED in the report; the run continues without its output.
        return True

    @staticmethod
    def _topo_order(nodes: list[AbstractNode]) -> list[AbstractNode]:
        """
        Topologically order sibling nodes by their ``consumes`` edges (Kahn, declaration-stable).

        Args:
            nodes (list[AbstractNode]): The sibling nodes (unordered).

        Returns:
            list[AbstractNode]: A valid execution order.

        Raises:
            PipelineError: On an unknown dependency reference or a dependency cycle.
        """
        # 1. Validate every consumed key resolves to a sibling.
        by_key = {n.key: n for n in nodes}
        for node in nodes:
            for dep in node.consumes():
                if dep not in by_key:
                    raise PipelineError(
                        f"Node {node.key!r} consumes {dep!r} but no sibling produces it.",
                        node_key=node.key,
                        code="unknown_dependency",
                    )

        # 2. Kahn's algorithm, preserving declaration order among ready nodes.
        remaining = list(nodes)
        resolved: set[str] = set()
        ordered: list[AbstractNode] = []
        while remaining:
            ready = [n for n in remaining if all(dep in resolved for dep in n.consumes())]
            if not ready:
                cyclic = ", ".join(n.key for n in remaining)
                raise PipelineError(
                    f"Cycle in the node dependency graph among: {cyclic}.",
                    code="dependency_cycle",
                )
            for node in ready:
                ordered.append(node)
                resolved.add(node.key)
                remaining.remove(node)
        return ordered


__all__ = ["PipelineEngine"]

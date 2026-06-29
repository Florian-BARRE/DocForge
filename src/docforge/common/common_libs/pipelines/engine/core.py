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
import time

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from ..base import (
    AbstractNode,
    CachePolicy,
    CompositeNode,
    ContextBase,
    ErrorPolicy,
    NodeOutput,
    PipelineError,
    RunContext,
    ServiceRegistry,
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
        self.logger.info(f"Pipeline {root.key!r} started.")
        await self._hooks.prepare(run)

        # 2. The root's input IS the run input — it is provided directly, never resolved from
        # bindings (a pipeline is the source of the run data, not a consumer of upstream outputs).
        output, report, _error = await self._run_node(
            root, run.run_input, None, run.services, run, {}
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
        parent_ctx: "ContextBase | None",
        registry: "ServiceRegistry",
        run: "RunContext",
        siblings: dict[str, NodeOutput],
    ) -> tuple[NodeOutput | None, NodeReport, "PipelineError | None"]:
        """
        Run a single node (composite or leaf), capturing its outcome into a report (never raising).

        Args:
            node (AbstractNode): The node to run.
            node_input (NodeOutput): The node's already-resolved typed Input.
            parent_ctx (ContextBase | None): The parent node's context (None at the root); the
                child's context links to it so a node can walk up the tree.
            registry (ServiceRegistry): The service registry visible at the parent level.
            run (RunContext): The run-wide state.
            siblings (dict[str, NodeOutput]): Outputs of this node's already-run siblings.

        Returns:
            tuple[NodeOutput | None, NodeReport, PipelineError | None]: The node output (None on
                failure), its report, and the failure (the wrapped error the parent re-wraps), or
                None when the node succeeded.
        """
        # 1. Push this node's local services so its subtree can resolve them (vertical axis).
        local = node.local_services()
        scoped_registry = registry.child(local) if local else registry

        report = NodeReport(
            key=node.key,
            kind=str(node.KIND),
            inputs=list(type(node_input).model_fields.keys()),
        )
        started = time.perf_counter()
        output: NodeOutput | None = None
        error: PipelineError | None = None
        try:
            # 2. Resolve the node's required services and build its concrete context.
            services = Resolver.resolve_services(node, scoped_registry)
            ctx = node.Context(node_input, services, parent_ctx)

            # 3. Composite -> drive children (it re-wraps a failing child in node.Error); leaf ->
            # run the work through the middleware (its execute may raise its own typed error).
            if isinstance(node, CompositeNode):
                output = await self._run_composite(node, ctx, scoped_registry, run, report)
            else:
                output = await self._run_leaf(node, ctx, run, report)
            if report.status == ReportStatus.PENDING:
                report.status = ReportStatus.OK
        except PipelineError as exc:
            error = exc
            report.status = ReportStatus.FAILED
            report.error = ErrorInfo.from_exception(exc)
            self.logger.warning(f"Node {node.key!r} failed ({exc.code}): {exc}")
            await self._hooks.on_error(node, exc, run)
        except Exception as exc:  # wrap a raw exception in THIS node's own Error type
            wrapped = node.Error(str(exc), node_key=node.key, node_kind=node.KIND, cause=exc)
            error = wrapped
            report.status = ReportStatus.FAILED
            report.error = ErrorInfo.from_exception(wrapped)
            self.logger.warning(f"Node {node.key!r} raised {type(exc).__name__}: {exc}")
            await self._hooks.on_error(node, wrapped, run)
        finally:
            report.duration_ms = int((time.perf_counter() - started) * 1000)
        return output, report, error

    async def _run_composite(
        self,
        node: CompositeNode,
        ctx: "ContextBase",
        registry: "ServiceRegistry",
        run: "RunContext",
        report: NodeReport,
    ) -> NodeOutput | None:
        """
        Topologically drive a composite's children, applying each child's error policy.

        Args:
            node (CompositeNode): The composite node.
            ctx (ContextBase): The composite's own context — its ``input`` is the children's parent
                input and ``ctx`` itself is their parent context.
            registry (ServiceRegistry): The registry visible to the children.
            run (RunContext): The run-wide state.
            report (NodeReport): The composite's report (children appended here).

        Returns:
            NodeOutput | None: The aggregated output, or None when a FAIL child propagated.
        """
        outputs: dict[str, NodeOutput] = {}
        for child in self._topo_order(node.children):
            # 1. Resolve the child's typed input; a resolution failure is a child failure.
            try:
                child_input = Resolver.build_input(child, run.run_input, ctx.input, outputs)
            except PipelineError as exc:
                child_report = NodeReport(
                    key=child.key, kind=str(child.KIND), status=ReportStatus.FAILED,
                    error=ErrorInfo.from_exception(exc),
                )
                report.add_child(child_report)
                self._apply_child_policy(node, child, exc)  # raises node.Error if FAIL
                continue

            # 2. Run the child (linking it to this composite's context); record its report.
            child_output, child_report, child_error = await self._run_node(
                child, child_input, ctx, registry, run, outputs
            )
            report.add_child(child_report)

            # 3. On child failure, apply its authoritative policy: FAIL re-wraps + propagates,
            # SKIP/DEGRADE continue without the child's output.
            if child_error is not None:
                self._apply_child_policy(node, child, child_error)
                continue

            # 4. Success -> publish the child's output for its downstream siblings.
            if child_output is not None:
                outputs[child.key] = child_output

        return node.aggregate(outputs)

    async def _run_leaf(
        self,
        node: AbstractNode,
        ctx: "ContextBase",
        run: "RunContext",
        report: NodeReport,
    ) -> NodeOutput | None:
        """
        Run a leaf node through the gate / cache / hook middleware.

        Args:
            node (AbstractNode): The leaf node.
            ctx (ContextBase): The node's resolved context (input + services), passed to ``execute``.
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

        # 3. Miss — pre-run prep, execute (the node reads its context), then store + post-run.
        await self._hooks.before_node(node, run)
        output = await node.execute(ctx)
        if getattr(node.SPEC, "cache_policy", None) == CachePolicy.NODE_CACHED:
            await self._hooks.cache_store(node, output, run)
        await self._hooks.after_node(node, output, run)
        return output

    @staticmethod
    def _apply_child_policy(
        parent: "CompositeNode", child: AbstractNode, child_error: "PipelineError"
    ) -> None:
        """
        Apply a failed child's authoritative error policy.

        On FAIL, the parent RE-WRAPS the child's error in its own ``Error`` type (with the child
        error as ``cause``) and raises it — so the failure climbs the tree as a recursive cause
        chain (step error -> stage error -> pipeline error). On SKIP/DEGRADE, it returns and the run
        continues without the child's output.

        Args:
            parent (CompositeNode): The composite whose child failed.
            child (AbstractNode): The failed child.
            child_error (PipelineError): The child's failure (becomes the wrapped ``cause``).

        Raises:
            PipelineError: The parent's wrapped error, when the child's policy is FAIL.
        """
        if child.error_policy == ErrorPolicy.FAIL:
            raise parent.Error(
                f"{parent.KIND}:{parent.key!r} failed because child {child.key!r} failed.",
                node_key=parent.key,
                node_kind=parent.KIND,
                cause=child_error,
            )
        # SKIP / DEGRADE — the child stays FAILED in the report; the run continues without its output.

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

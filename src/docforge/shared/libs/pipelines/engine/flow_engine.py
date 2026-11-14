# ====== Code Summary ======
# The pipeline engine. Given a Group (the graph root) and a run input, it walks the group's nodes
# by their transitions, resolves each node's input from the wiring, runs it, and records what
# happened — emitting a NodeExecutionRecord tree (even on success). Sequence, escalation and
# fallback all fall out of the transitions + conditions; a failure with an OnFailure edge escalates,
# a failure without one is decided by the node's ErrorPolicy. The engine is external and generic:
# it hardcodes no stage order and knows nothing about specific node kinds. FlowEngine is the walker
# (transition selection, the record-not-crash top loop, the timeout); running one action and
# running a foreach are delegated to ActionRunner and ForEachRunner.

# ====== Standard Library Imports ======
import asyncio
from time import perf_counter
from traceback import format_exc
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    AbstractNode,
    ActionNode,
    ErrorInfo,
    ErrorPolicy,
    ForEach,
    Group,
    NodeExecutionRecord,
    NodeOutput,
    NodeStatus,
)

# ====== Local Project Imports ======
from .action_runner import ActionRunner
from .cache import CacheHook
from .context import RunContext
from .errors import EngineInvariantError
from .foreach_runner import ForEachRunner
from .navigation import GraphNavigator
from .progress import ProgressCallback, ProgressPhase
from .progress_emitter import ProgressEmitter
from .resolver import InputResolver, ResolutionError
from .resume import ResumePoint
from .trace import TraceLevel
from .trace_capture import TraceCapture


class FlowEngine(LoggerClass):
    """
    Executes a pipeline graph.

    Runs a Group by walking its transitions from the entry node, resolving each node's input from
    the group's bindings, running it, and emitting a NodeExecutionRecord. The engine is stateless
    across runs; all run-scoped state lives in the RunContext.

    Deliberately keeps the execution loop whole (one tightly-coupled unit: running + recording +
    progress). Its stateless concerns are delegated to helpers — graph navigation to GraphNavigator,
    trace payload capture to TraceCapture, running one action to ActionRunner and a foreach to
    ForEachRunner — while the loop itself is not fragmented across modules.
    """

    def __init__(self, trace_level: TraceLevel = TraceLevel.FULL) -> None:
        """
        Args:
            trace_level (TraceLevel): How much of each node's input/output is captured onto its
                execution record. ``off`` captures nothing (the search runner's mode — the record is
                discarded, so no per-hop trace work is spent). ``shape`` attaches only the cheap
                SHALLOW shape descriptor (the ingest default — no deep ``model_dump`` at every
                IR-carrying hop, no raw content at rest). ``full`` attaches that summary AND the full
                payload-stripped dump (the worker persists the latter to the object store). Defaults
                to ``full`` so a direct caller that reads the record gets everything.
        """
        LoggerClass.__init__(self)
        self._trace = TraceCapture(trace_level)
        self._actions = ActionRunner(self._trace)
        self._foreach = ForEachRunner(self._run_group)

    async def _dispatch(
        self,
        node: AbstractNode,
        group: Group,
        context: RunContext,
        group_input: dict[str, Any],
        node_outputs: dict[str, NodeOutput],
        at_root: bool = False,
    ) -> tuple[NodeOutput | None, NodeExecutionRecord]:
        """Run a child: an action directly, a foreach per item, a sub-group recursively.

        ``at_root`` is forwarded only to an action — the cache seam fires at a stage node (an action
        in the root group), never at a ForEach or a nested sub-group boundary.
        """
        if isinstance(node, ActionNode):
            return await self._actions.run(
                node, group, context, group_input, node_outputs, at_root=at_root
            )
        if isinstance(node, ForEach):
            return await self._foreach.run(node, group, context, group_input, node_outputs)
        if isinstance(node, Group):
            # A sub-group has no typed Consumes: resolve the parent's bindings for it into a dynamic
            # dict, which becomes the sub-group's input (its children read it via FromGroupInput).
            try:
                sub_group_input = InputResolver.resolve_mapping(
                    group.bindings.get(node.id, {}), context.run_input, group_input, node_outputs
                )
            except ResolutionError as exc:
                self.logger.error(f"Group '{node.id}' input resolution failed: {exc}")
                return None, NodeExecutionRecord(
                    node_id=node.id,
                    kind=node.KIND,
                    status=NodeStatus.FAILED,
                    duration_ms=0.0,
                    error=ErrorInfo(error_type="ResolutionError", message=str(exc)),
                )
            return await self._run_group(node, context, group_input=sub_group_input)
        # A node that is neither an action, a foreach, nor a sub-group can only enter the graph
        # through a code/build bug (the engine's own type system is violated) — never a data or
        # config failure. Raise the engine-invariant marker so execute() surfaces it LOUDLY rather
        # than masking a broken build as a recorded node failure.
        raise EngineInvariantError(
            f"unsupported node type in group '{group.id}': {type(node).__name__}"
        )

    async def _run_child(
        self,
        node: AbstractNode,
        group: Group,
        context: RunContext,
        group_input: dict[str, Any],
        node_outputs: dict[str, NodeOutput],
        at_root: bool = False,
    ) -> tuple[NodeOutput | None, NodeExecutionRecord]:
        """Run one child, wrapped in START/END progress events."""
        # A ForEach emits its OWN START from inside the ForEachRunner — once it has resolved the iterated
        # list, so the event can carry the item total for a live fan-out counter. Every other node
        # starts here (its width is not a concept).
        if not isinstance(node, ForEach):
            await ProgressEmitter.emit(context, ProgressPhase.START, node)
        node_output, record = await self._dispatch(
            node, group, context, group_input, node_outputs, at_root=at_root
        )
        await ProgressEmitter.emit(context, ProgressPhase.END, node, record)
        return node_output, record

    async def _run_group(
        self,
        group: Group,
        context: RunContext,
        group_input: dict[str, Any],
        is_root: bool = False,
    ) -> tuple[NodeOutput | None, NodeExecutionRecord]:
        """Walk a group from its entry node, following transitions, and record every step.

        ``is_root`` marks the OUTERMOST group (the pipeline itself). Only its direct action children
        are stage-node cache boundaries; sub-groups and ForEach bodies run with ``is_root`` False, so
        the cache seam never fires inside them.
        """
        started = perf_counter()
        node_outputs: dict[str, NodeOutput] = {}
        child_records: list[NodeExecutionRecord] = []
        group_status = NodeStatus.SUCCESS
        group_output: NodeOutput | None = None
        visited: set[str] = set()

        # A resumed (replay) run seeds the ROOT group's outputs with the persisted upstream artefacts
        # and starts at the requested stage instead of the entry; the seeded nodes never run (no
        # record, no progress) — downstream bindings resolve against the seeds exactly as in a full run.
        if is_root and context.resume is not None:
            node_outputs.update(context.resume.seeded_outputs)
            node = GraphNavigator.child_by_id(group, context.resume.start_node_id)
        else:
            node = GraphNavigator.entry(group)
        while node is not None:
            # 0. Guard against a cyclic graph that slipped past validation (no node runs twice).
            if node.id in visited:
                self.logger.error(f"Cycle detected in group '{group.id}' at node '{node.id}'")
                raise ValueError(f"Cycle detected in group '{group.id}' at node '{node.id}'.")
            visited.add(node.id)

            # 1. Run the child (START/END progress + action-vs-sub-group dispatch). Only the root
            #    group's direct children are stage-cache boundaries.
            node_output, record = await self._run_child(
                node, group, context, group_input, node_outputs, at_root=is_root
            )
            child_records.append(record)
            if node_output is not None:
                node_outputs[node.id] = node_output
                group_output = node_output

            # 2. Pick the next node from the outgoing transitions.
            next_node = GraphNavigator.next(group, node, record.status, node_output)

            # 3. A failure with no recovery edge hands control to the node's error policy.
            if next_node is None and record.status == NodeStatus.FAILED:
                if node.ERROR_POLICY == ErrorPolicy.FAIL:
                    group_status, group_output = NodeStatus.FAILED, None
                    break
                # SKIP: mark the node skipped (its error stays attached) and continue via its
                # success-path edge, treating the failure as a skip.
                record.status = NodeStatus.SKIPPED
                next_node = GraphNavigator.next(group, node, NodeStatus.SUCCESS, None)
                if next_node is None:
                    break

            node = next_node

        # 4. Emit the group's own record wrapping its children (heavy payloads stripped at the full
        #    tier, the cheap shape summary at the shape tier).
        group_full, group_summary = self._trace.capture(group_output)
        record = NodeExecutionRecord(
            node_id=group.id,
            kind=group.KIND,
            status=group_status,
            duration_ms=(perf_counter() - started) * 1000,
            output=group_full,
            output_summary=group_summary,
            children=child_records,
        )
        return group_output, record

    async def execute(
        self,
        group: Group,
        run_input: dict[str, Any],
        timeout_seconds: float | None = None,
        progress_callback: ProgressCallback | None = None,
        cache_hook: "CacheHook | None" = None,
        resume: ResumePoint | None = None,
    ) -> tuple[NodeOutput | None, NodeExecutionRecord]:
        """
        Execute a pipeline graph and return its output plus the full execution trace.

        Args:
            group (Group): The graph root to run.
            run_input (dict): The pipeline's external input (addressable by FromRunInput).
            timeout_seconds (float | None): Optional wall-clock deadline for the whole run; on
                timeout the run is cancelled and a FAILED record is returned.
            progress_callback (ProgressCallback | None): Optional async callback fired at each
                node's START and END (for a UI live-status feed).
            cache_hook (CacheHook | None): Optional stage-cache seam. When provided, a cacheable
                root stage is served from / stored into it; when None, the run is byte-for-byte the
                same as if the cache did not exist.
            resume (ResumePoint | None): Optional mid-graph start (replay from a stage): the root walk
                begins at ``start_node_id`` with ``seeded_outputs`` standing in for the upstream root
                nodes, which never run. An unknown start node is a recorded FAILED run. None runs
                from the entry, unchanged.

        Returns:
            tuple[NodeOutput | None, NodeExecutionRecord]: The final output (None if the run failed)
                and the recursive execution record.
        """
        self.logger.info(f"Running pipeline '{group.id}'")
        context = RunContext(
            run_input=run_input,
            progress_callback=progress_callback,
            cache_hook=cache_hook,
            resume=resume,
        )
        started = perf_counter()
        run = self._run_group(group, context, group_input=run_input, is_root=True)

        # 1. Run, optionally under a global timeout.
        try:
            if timeout_seconds is None:
                output, record = await run
            else:
                output, record = await asyncio.wait_for(run, timeout=timeout_seconds)
        except TimeoutError:
            self.logger.error(f"Pipeline '{group.id}' timed out after {timeout_seconds}s")
            return None, NodeExecutionRecord(
                node_id=group.id,
                kind=group.KIND,
                status=NodeStatus.FAILED,
                duration_ms=(perf_counter() - started) * 1000,
                error=ErrorInfo(
                    error_type="TimeoutError", message=f"pipeline exceeded {timeout_seconds}s"
                ),
            )
        except EngineInvariantError:
            # A genuinely-unrecoverable violation of the engine's OWN construction invariants (a
            # graph node whose type the engine does not support) — a code/build bug, not a run
            # failure. Surface it LOUDLY rather than masking it as a recorded FAILED run.
            self.logger.error(f"Pipeline '{group.id}' hit an engine-invariant violation")
            raise
        except Exception as exc:
            # Record-not-crash contract, honoured UNIFORMLY: any OTHER escape — a structural raise
            # the validator should have caught (a cycle, a bad entry count, a dangling transition
            # target) OR an unexpected internal engine error — becomes a FAILED record so the caller
            # (the runner) sees the documented recorded-failure, never a raw crash. The lone
            # exception is a progress callback that raised: that is caller-owned control flow (the
            # worker's cooperative-cancel guard), so it propagates UNCHANGED — the run's CANCELLED
            # semantics stay intact. (asyncio.CancelledError is a BaseException and bypasses this net
            # entirely, so a worker shutdown/timeout still tears the task down as before.)
            if context.callback_error is not None and context.callback_error is exc:
                raise
            self.logger.exception(f"Pipeline '{group.id}' crashed; recording a FAILED run: {exc}")
            return None, NodeExecutionRecord(
                node_id=group.id,
                kind=group.KIND,
                status=NodeStatus.FAILED,
                duration_ms=(perf_counter() - started) * 1000,
                error=ErrorInfo(
                    error_type=type(exc).__name__, message=str(exc), traceback=format_exc()
                ),
            )

        # 2. Report the outcome.
        self.logger.info(
            f"Pipeline '{group.id}' finished: {record.status} in {record.duration_ms:.1f}ms"
        )
        return output, record


__all__ = ["FlowEngine"]

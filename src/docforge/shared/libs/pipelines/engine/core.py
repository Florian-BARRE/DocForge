# ====== Code Summary ======
# The pipeline engine. Given a Group (the graph root) and a run input, it walks the group's nodes
# by their transitions, resolves each node's input from the wiring, runs it, and records what
# happened — emitting a NodeExecutionRecord tree (even on success). Sequence, escalation and
# fallback all fall out of the transitions + conditions; a failure with an OnFailure edge escalates,
# a failure without one is decided by the node's ErrorPolicy. The engine is external and generic:
# it hardcodes no stage order and knows nothing about specific node kinds.

# ====== Standard Library Imports ======
import asyncio
from time import perf_counter
from traceback import format_exc
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from pydantic import BaseModel, ValidationError

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    AbstractNode,
    ActionNode,
    Always,
    Condition,
    ErrorInfo,
    ErrorPolicy,
    ForEach,
    ForEachItems,
    GraphTopology,
    Group,
    NodeExecutionRecord,
    NodeOutput,
    NodeStatus,
    OnFailure,
    OnSuccess,
    ScoreBelow,
    ScoredOutput,
    WhenEquals,
)

# ====== Local Project Imports ======
from .context import RunContext
from .progress import ProgressCallback, ProgressEvent, ProgressPhase
from .resolver import InputResolver, ResolutionError


class FlowEngine(LoggerClass):
    """
    Executes a pipeline graph.

    Runs a Group by walking its transitions from the entry node, resolving each node's input from
    the group's bindings, running it, and emitting a NodeExecutionRecord. The engine is stateless
    across runs; all run-scoped state lives in the RunContext.

    Deliberately a single cohesive class (one tightly-coupled execution loop: navigation + running
    + recording + progress); its pure graph algorithms live in GraphTopology, but the loop itself
    is kept whole rather than fragmented across modules.
    """

    def __init__(self, trace_payloads: bool = True) -> None:
        """
        Args:
            trace_payloads (bool): When True (default), each node's resolved input + output is
                serialised (payload-stripped) into its execution record — a debugging aid. The
                ingestion/search runners DISCARD the record, so they pass False to skip ~2 full-IR
                ``model_dump`` + strip traversals at *every* node hop (the IR flows through ~10
                IR-carrying hops per document). Set True only when a caller actually reads the trace.
        """
        LoggerClass.__init__(self)
        self._trace_payloads = trace_payloads

    def __entry(self, group: Group) -> AbstractNode | None:
        """Return the group's entry node — the single child with no incoming transition."""
        # 1. An empty group has nothing to run.
        if not group.children:
            return None
        # 2. Exactly one entry (a child that is never a transition target) is required.
        entries = GraphTopology.entries({child.id for child in group.children}, group.transitions)
        if len(entries) != 1:
            self.logger.error(
                f"Group '{group.id}' must have exactly one entry node, found {len(entries)}"
            )
            raise ValueError(
                f"Group '{group.id}' must have exactly one entry node, found {len(entries)}."
            )
        return self.__child_by_id(group, entries[0])

    def __child_by_id(self, group: Group, node_id: str) -> AbstractNode:
        """Return the child node with the given id, or fail loudly."""
        for child in group.children:
            if child.id == node_id:
                return child
        self.logger.error(f"Group '{group.id}' has no child '{node_id}' referenced by a transition")
        raise ValueError(f"Group '{group.id}' has no child '{node_id}' referenced by a transition.")

    # A numeric list longer than this (an embedding vector) is compacted in the records.
    _NUMERIC_LIST_LIMIT = 64

    @classmethod
    def __strip_payloads(cls, value: Any) -> Any:
        """Replace heavy payloads (bytes, long numeric lists) with size placeholders, recursively."""
        if isinstance(value, bytes):
            return f"<{len(value)} bytes>"
        if isinstance(value, dict):
            return {key: cls.__strip_payloads(item) for key, item in value.items()}
        if isinstance(value, list):
            # An embedding vector in a trace is dead weight — keep its size, drop its numbers.
            if len(value) > cls._NUMERIC_LIST_LIMIT and all(
                isinstance(item, (int, float)) and not isinstance(item, bool) for item in value
            ):
                return f"<{len(value)} numbers>"
            return [cls.__strip_payloads(item) for item in value]
        return value

    @classmethod
    def __dump(cls, model: BaseModel) -> dict[str, Any]:
        """Dump a model for an execution record WITHOUT its heavy payloads (crops, vectors…) — a
        record is a trace, not a store; re-serialising every image or embedding at every hop
        multiplies a document's memory footprint several-fold."""
        return cls.__strip_payloads(model.model_dump())

    def __condition_matches(
        self, condition: Condition, status: NodeStatus, output: NodeOutput | None
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
                self.logger.warning(f"ScoreBelow transition skipped: output is not a ScoredOutput")
                return False
            return output.score < condition.threshold
        if isinstance(condition, WhenEquals):
            # Value routing only applies to a SUCCESSFUL output carrying the field.
            if status != NodeStatus.SUCCESS or output is None:
                return False
            if not hasattr(output, condition.field):
                self.logger.warning(
                    f"WhenEquals transition skipped: output has no field '{condition.field}'"
                )
                return False
            return str(getattr(output, condition.field)) == condition.equals
        return False

    def __condition_rank(self, condition: Condition) -> int:
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

    def __next(
        self, group: Group, node: AbstractNode, status: NodeStatus, output: NodeOutput | None
    ) -> AbstractNode | None:
        """Return the next node to run — the MOST SPECIFIC matching outgoing transition (None = terminal)."""
        outgoing = [t for t in group.transitions if t.from_node_id == node.id]
        outgoing.sort(key=lambda t: self.__condition_rank(t.condition), reverse=True)
        for transition in outgoing:
            if self.__condition_matches(transition.condition, status, output):
                return self.__child_by_id(group, transition.to_node_id)
        return None

    async def __run_action(
        self,
        node: ActionNode,
        group: Group,
        context: RunContext,
        group_input: dict[str, Any],
        node_outputs: dict[str, NodeOutput],
    ) -> tuple[NodeOutput | None, NodeExecutionRecord]:
        """Resolve, run and record a single action node."""
        started = perf_counter()
        self.logger.debug(f"Running node '{node.id}' ({node.KIND})")

        # 1. Resolve the node's input from its bindings; a wiring miss (ResolutionError) or an
        #    off-type value (pydantic ValidationError from the Consumes model) is a FAILED record —
        #    never a whole-run crash.
        node_bindings = group.bindings.get(node.id, {})
        try:
            node_input = InputResolver.resolve(
                node.Consumes, node_bindings, context.run_input, group_input, node_outputs
            )
        except (ResolutionError, ValidationError) as exc:
            self.logger.error(f"Node '{node.id}' input resolution failed: {exc}")
            return None, NodeExecutionRecord(
                node_id=node.id,
                kind=node.KIND,
                status=NodeStatus.FAILED,
                duration_ms=(perf_counter() - started) * 1000,
                error=ErrorInfo(error_type=type(exc).__name__, message=str(exc)),
            )

        # 2. Run the node, capturing success or failure.
        try:
            node_output: NodeOutput | None = await node.run(node_input)
            status = NodeStatus.SUCCESS
            error = None
        except Exception as exc:
            node_output = None
            status = NodeStatus.FAILED
            error = ErrorInfo(
                error_type=type(exc).__name__, message=str(exc), traceback=format_exc()
            )
            self.logger.warning(f"Node '{node.id}' failed: {type(exc).__name__}: {exc}")

        # 3. Build the execution record (byte payloads stripped — a trace, not a store).
        record = NodeExecutionRecord(
            node_id=node.id,
            kind=node.KIND,
            status=status,
            duration_ms=(perf_counter() - started) * 1000,
            resolved_input=self.__dump(node_input) if self._trace_payloads else None,
            output=(
                self.__dump(node_output)
                if (self._trace_payloads and node_output is not None)
                else None
            ),
            error=error,
        )
        if status == NodeStatus.SUCCESS:
            self.logger.debug(f"Node '{node.id}' succeeded in {record.duration_ms:.1f}ms")
        return node_output, record

    async def __run_foreach(
        self,
        node: ForEach,
        group: Group,
        context: RunContext,
        group_input: dict[str, Any],
        node_outputs: dict[str, NodeOutput],
    ) -> tuple[NodeOutput | None, NodeExecutionRecord]:
        """Run a foreach: resolve its list, run the body once per item (bounded), collect in order."""
        started = perf_counter()

        # 1. Resolve the list the loop iterates over; a wiring miss or a non-list is a FAILED record.
        try:
            over_value = InputResolver.resolve_mapping(
                {"over": node.over}, context.run_input, group_input, node_outputs
            )["over"]
        except ResolutionError as exc:
            self.logger.error(f"ForEach '{node.id}' list resolution failed: {exc}")
            return None, NodeExecutionRecord(
                node_id=node.id,
                kind=node.KIND,
                status=NodeStatus.FAILED,
                duration_ms=(perf_counter() - started) * 1000,
                error=ErrorInfo(error_type="ResolutionError", message=str(exc)),
            )
        if not isinstance(over_value, list):
            message = f"'over' must resolve to a list, got {type(over_value).__name__}"
            self.logger.error(f"ForEach '{node.id}': {message}")
            return None, NodeExecutionRecord(
                node_id=node.id,
                kind=node.KIND,
                status=NodeStatus.FAILED,
                duration_ms=(perf_counter() - started) * 1000,
                error=ErrorInfo(error_type="ValueError", message=message),
            )

        # 2. The collection contract must hold before anything is spent (the validator's rule,
        #    re-checked here so an unvalidated graph still fails loudly, never silently).
        expected = node.item_type()
        if expected is None:
            message = "the body violates the collection contract (uniform single-slot terminals)"
            self.logger.error(f"ForEach '{node.id}': {message}")
            return None, NodeExecutionRecord(
                node_id=node.id,
                kind=node.KIND,
                status=NodeStatus.FAILED,
                duration_ms=(perf_counter() - started) * 1000,
                error=ErrorInfo(error_type="ValueError", message=message),
            )

        # 3. Run the body once per item, bounded by max_concurrency; gather preserves item order.
        semaphore = asyncio.Semaphore(node.max_concurrency)

        async def run_item(item: Any) -> tuple[NodeOutput | None, NodeExecutionRecord]:
            async with semaphore:
                return await self._run_group(
                    node.body, context, group_input={node.item_field: item}
                )

        runs = await asyncio.gather(*(run_item(item) for item in over_value))

        # 4. Collect each item's terminal value, failing loudly on any item that failed or whose
        #    runtime path ended off-contract (e.g. an unmatched switch value stopping mid-graph).
        child_records: list[NodeExecutionRecord] = []
        items: list[Any] = []
        failure: str | None = None
        for index, (item_output, item_record) in enumerate(runs):
            item_record.node_id = f"{node.body.id}[{index}]"
            child_records.append(item_record)
            if failure is not None:
                continue
            if item_record.status == NodeStatus.FAILED or item_output is None:
                failure = f"item {index} failed"
                continue
            fields = type(item_output).model_fields
            value = getattr(item_output, next(iter(fields))) if len(fields) == 1 else None
            if not isinstance(value, expected):
                failure = (
                    f"item {index} ended on '{type(item_output).__name__}' — every runtime path "
                    f"must end on the body's terminal artefact '{expected.__name__}'"
                )
                continue
            items.append(value)

        # 5. Emit the foreach record wrapping the per-item runs. The record keeps only the item
        #    COUNT: the values already live in the child records, and dumping them again would
        #    duplicate every collected artefact (e.g. figure crops) in the trace.
        if failure is not None:
            self.logger.warning(f"ForEach '{node.id}' failed: {failure}")
        output = None if failure is not None else ForEachItems(items=items)
        return output, NodeExecutionRecord(
            node_id=node.id,
            kind=node.KIND,
            status=NodeStatus.FAILED if failure is not None else NodeStatus.SUCCESS,
            duration_ms=(perf_counter() - started) * 1000,
            output={"items_count": len(items)} if output is not None else None,
            error=ErrorInfo(error_type="ForEachError", message=failure) if failure else None,
            children=child_records,
        )

    async def __emit(
        self,
        context: RunContext,
        phase: ProgressPhase,
        node: AbstractNode,
        record: NodeExecutionRecord | None = None,
    ) -> None:
        """Fire the run's progress callback for a node event, if one is registered."""
        if context.progress_callback is None:
            return
        await context.progress_callback(
            ProgressEvent(phase=phase, node_id=node.id, kind=node.KIND, record=record)
        )

    async def __dispatch(
        self,
        node: AbstractNode,
        group: Group,
        context: RunContext,
        group_input: dict[str, Any],
        node_outputs: dict[str, NodeOutput],
    ) -> tuple[NodeOutput | None, NodeExecutionRecord]:
        """Run a child: an action directly, a foreach per item, a sub-group recursively."""
        if isinstance(node, ActionNode):
            return await self.__run_action(node, group, context, group_input, node_outputs)
        if isinstance(node, ForEach):
            return await self.__run_foreach(node, group, context, group_input, node_outputs)
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
        raise TypeError(f"Unsupported node type in group '{group.id}': {type(node).__name__}")

    async def __run_child(
        self,
        node: AbstractNode,
        group: Group,
        context: RunContext,
        group_input: dict[str, Any],
        node_outputs: dict[str, NodeOutput],
    ) -> tuple[NodeOutput | None, NodeExecutionRecord]:
        """Run one child, wrapped in START/END progress events."""
        await self.__emit(context, ProgressPhase.START, node)
        node_output, record = await self.__dispatch(node, group, context, group_input, node_outputs)
        await self.__emit(context, ProgressPhase.END, node, record)
        return node_output, record

    async def _run_group(
        self, group: Group, context: RunContext, group_input: dict[str, Any]
    ) -> tuple[NodeOutput | None, NodeExecutionRecord]:
        """Walk a group from its entry node, following transitions, and record every step."""
        started = perf_counter()
        node_outputs: dict[str, NodeOutput] = {}
        child_records: list[NodeExecutionRecord] = []
        group_status = NodeStatus.SUCCESS
        group_output: NodeOutput | None = None
        visited: set[str] = set()

        node = self.__entry(group)
        while node is not None:
            # 0. Guard against a cyclic graph that slipped past validation (no node runs twice).
            if node.id in visited:
                self.logger.error(f"Cycle detected in group '{group.id}' at node '{node.id}'")
                raise ValueError(f"Cycle detected in group '{group.id}' at node '{node.id}'.")
            visited.add(node.id)

            # 1. Run the child (START/END progress + action-vs-sub-group dispatch).
            node_output, record = await self.__run_child(
                node, group, context, group_input, node_outputs
            )
            child_records.append(record)
            if node_output is not None:
                node_outputs[node.id] = node_output
                group_output = node_output

            # 2. Pick the next node from the outgoing transitions.
            next_node = self.__next(group, node, record.status, node_output)

            # 3. A failure with no recovery edge hands control to the node's error policy.
            if next_node is None and record.status == NodeStatus.FAILED:
                if node.ERROR_POLICY == ErrorPolicy.FAIL:
                    group_status, group_output = NodeStatus.FAILED, None
                    break
                # SKIP: mark the node skipped (its error stays attached) and continue via its
                # success-path edge, treating the failure as a skip.
                record.status = NodeStatus.SKIPPED
                next_node = self.__next(group, node, NodeStatus.SUCCESS, None)
                if next_node is None:
                    break

            node = next_node

        # 4. Emit the group's own record wrapping its children (byte payloads stripped).
        record = NodeExecutionRecord(
            node_id=group.id,
            kind=group.KIND,
            status=group_status,
            duration_ms=(perf_counter() - started) * 1000,
            output=(
                self.__dump(group_output)
                if (self._trace_payloads and group_output is not None)
                else None
            ),
            children=child_records,
        )
        return group_output, record

    async def execute(
        self,
        group: Group,
        run_input: dict[str, Any],
        timeout_seconds: float | None = None,
        progress_callback: ProgressCallback | None = None,
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

        Returns:
            tuple[NodeOutput | None, NodeExecutionRecord]: The final output (None if the run failed)
                and the recursive execution record.
        """
        self.logger.info(f"Running pipeline '{group.id}'")
        context = RunContext(run_input=run_input, progress_callback=progress_callback)
        started = perf_counter()
        run = self._run_group(group, context, group_input=run_input)

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

        # 2. Report the outcome.
        self.logger.info(
            f"Pipeline '{group.id}' finished: {record.status} in {record.duration_ms:.1f}ms"
        )
        return output, record


__all__ = ["FlowEngine"]

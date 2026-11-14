# ====== Code Summary ======
# Runs a ForEach node for the engine: resolves the list it iterates over, announces the fan-out START
# (carrying the item total), runs the body once per item bounded by ``max_concurrency`` (a semaphore;
# ``asyncio.gather`` keeps item order) and collects each item's terminal value in order, failing
# loudly on an item that failed or ended off-contract. The body is walked through the engine's own
# group walker, injected as ``run_group``, so the runner never imports the engine.

# ====== Standard Library Imports ======
import asyncio
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    ErrorInfo,
    ForEach,
    ForEachItems,
    Group,
    NodeExecutionRecord,
    NodeOutput,
    NodeStatus,
)

# ====== Local Project Imports ======
from .context import RunContext
from .progress import ProgressPhase
from .progress_emitter import ProgressEmitter
from .resolver import InputResolver, ResolutionError

# The engine's group walker: (group, context, group_input=...) -> (output, record).
RunGroup = Callable[..., Awaitable[tuple[NodeOutput | None, NodeExecutionRecord]]]


class ForEachRunner(LoggerClass):
    """Runs a foreach: resolves its list, runs the body once per item (bounded), collects in order."""

    def __init__(self, run_group: RunGroup) -> None:
        """
        Args:
            run_group (RunGroup): The engine's group walker, used to run the body for each item.
        """
        LoggerClass.__init__(self)
        self._run_group = run_group

    async def run(
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

        # 1b. The list is known — announce the fan-out START now, carrying its width so a consumer
        #     can show a live "done / total" counter. Emitted here (not in the walker's child step) because only
        #     after resolving ``over`` is the item total known.
        await ProgressEmitter.emit(context, ProgressPhase.START, node, total_items=len(over_value))

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

        # 3. Run the body once per item (bounded) and collect each terminal value in order.
        child_records, items, failure = await self._collect_items(
            node, context, group_input, over_value, expected
        )

        # 4. Emit the foreach record wrapping the per-item runs. The record keeps only the item
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

    async def _collect_items(
        self,
        node: ForEach,
        context: RunContext,
        group_input: dict[str, Any],
        over_value: list[Any],
        expected: type,
    ) -> tuple[list[NodeExecutionRecord], list[Any], str | None]:
        """
        Run a foreach body once per item and collect each item's terminal value in order.

        Runs the body bounded by ``max_concurrency`` (a semaphore); ``asyncio.gather`` preserves
        item order. Each item's terminal value is collected, failing loudly on any item that failed
        or whose runtime path ended off-contract (e.g. an unmatched switch value stopping mid-graph).

        Args:
            node (ForEach): The foreach node (supplies ``body``, ``item_field``, ``max_concurrency``).
            context (RunContext): The run-scoped context threaded into each item's sub-run.
            group_input (dict[str, Any]): The enclosing group input passed to each item's sub-run.
            over_value (list[Any]): The already-resolved list the loop iterates over.
            expected (type): The body's terminal artefact type every item must end on.

        Returns:
            tuple[list[NodeExecutionRecord], list[Any], str | None]: The per-item execution records
                (one per item, in order), the collected terminal values, and a failure message
                (None when every item succeeded on-contract).
        """
        # 1. Run the body once per item, bounded by max_concurrency; gather preserves item order.
        semaphore = asyncio.Semaphore(node.max_concurrency)

        async def run_item(item: Any) -> tuple[NodeOutput | None, NodeExecutionRecord]:
            async with semaphore:
                return await self._run_group(
                    node.body, context, group_input={node.item_field: item}
                )

        runs = await asyncio.gather(*(run_item(item) for item in over_value))

        # 2. Collect each item's terminal value, failing loudly on any item that failed or whose
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

        return child_records, items, failure


__all__ = ["ForEachRunner"]

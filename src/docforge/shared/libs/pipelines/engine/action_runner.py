# ====== Code Summary ======
# Runs ONE action node for the engine: resolves its input from the group's bindings, consults the
# stage-cache seam at a root boundary, runs the node and records the outcome as a NodeExecutionRecord.
# A wiring miss, an off-type input or a node exception is a FAILED record, never a whole-run crash.
# The runner is stateless across runs; the trace level lives in the shared TraceCapture.

# ====== Standard Library Imports ======
from time import perf_counter
from traceback import format_exc
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from pydantic import ValidationError

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    ActionNode,
    ErrorInfo,
    Group,
    NodeExecutionRecord,
    NodeOutput,
    NodeStatus,
)

# ====== Local Project Imports ======
from .context import RunContext
from .resolver import InputResolver, ResolutionError
from .trace_capture import TraceCapture


class ActionRunner(LoggerClass):
    """Resolves, runs and records a single action node (consulting the cache seam at the root)."""

    def __init__(self, trace: TraceCapture) -> None:
        """
        Args:
            trace (TraceCapture): The engine's payload capture, shared with the other runners.
        """
        LoggerClass.__init__(self)
        self._trace = trace

    async def run(
        self,
        node: ActionNode,
        group: Group,
        context: RunContext,
        group_input: dict[str, Any],
        node_outputs: dict[str, NodeOutput],
        at_root: bool = False,
    ) -> tuple[NodeOutput | None, NodeExecutionRecord]:
        """Resolve, run and record a single action node (consulting the cache seam at the root)."""
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

        # 1b. Cache seam — ONLY at a root-stage boundary, ONLY when a hook is attached AND the node
        #     declares itself cacheable. A HIT serves the stored artefact and SKIPS ``run`` entirely;
        #     the cached output flows on exactly like a fresh one (it carries any score a ScoreBelow
        #     edge reads). The engine knows nothing of keys/storage — it just calls the seam.
        if at_root and context.cache_hook is not None and getattr(node, "CACHEABLE", False):
            # Defensive boundary: the CacheHook contract is "never raises" (its impl swallows its own
            # storage/load errors and returns None on a miss), but a buggy hook must NEVER fail an
            # otherwise-good run — an escaped error degrades to a cache miss, not a failed node.
            try:
                cached = await context.cache_hook.before(node.id, node_input)
            except Exception as exc:
                self.logger.warning(
                    f"Node '{node.id}' cache lookup errored; treating as miss: {exc}"
                )
                cached = None
            if cached is not None:
                self.logger.debug(f"Node '{node.id}' served from cache")
                # Lift the score off the cached output too (mirror of the fresh-run lift below): the
                # cached artefact carries the same ``score`` a ScoreBelow edge reads, so the record
                # must report it identically whether the stage ran or was served from cache.
                cached_in_full, cached_in_summary = self._trace.capture(node_input)
                cached_out_full, cached_out_summary = self._trace.capture(cached)
                return cached, NodeExecutionRecord(
                    node_id=node.id,
                    kind=node.KIND,
                    status=NodeStatus.SUCCESS,
                    duration_ms=(perf_counter() - started) * 1000,
                    resolved_input=cached_in_full,
                    output=cached_out_full,
                    input_summary=cached_in_summary,
                    output_summary=cached_out_summary,
                    score=getattr(cached, "score", None),
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

        # 3. Build the execution record (byte payloads stripped — a trace, not a store). Token usage
        #    AND the quality score both ride on the RETURNED output (a paid text-gen node stamps
        #    ``_usage``; a scored node carries ``score``): lifting them from the output — not the node —
        #    is race-free under a ForEach that runs one node instance concurrently over items, and needs
        #    no reset between runs. ``getattr`` keeps each read defensive (a capture miss must never
        #    fail a node); a non-scored output simply has no ``score``, yielding None.
        input_full, input_summary = self._trace.capture(node_input)
        output_full, output_summary = self._trace.capture(node_output)
        record = NodeExecutionRecord(
            node_id=node.id,
            kind=node.KIND,
            status=status,
            duration_ms=(perf_counter() - started) * 1000,
            resolved_input=input_full,
            output=output_full,
            input_summary=input_summary,
            output_summary=output_summary,
            error=error,
            usage=getattr(node_output, "_usage", None) if node_output is not None else None,
            score=getattr(node_output, "score", None) if node_output is not None else None,
        )
        if status == NodeStatus.SUCCESS:
            self.logger.debug(f"Node '{node.id}' succeeded in {record.duration_ms:.1f}ms")
            # 3b. Cache seam (store) — mirror of the lookup above: a freshly-run cacheable root node
            #     hands its output to the seam to persist for a future run. Best-effort by contract
            #     (the seam swallows its own storage errors), so it never turns a good run into a
            #     failure.
            if (
                at_root
                and context.cache_hook is not None
                and node_output is not None
                and getattr(node, "CACHEABLE", False)
            ):
                # Defensive boundary (mirror of the lookup): a hook that lets a store error escape must
                # never fail a run that already succeeded — swallow + log, the output still flows on.
                try:
                    await context.cache_hook.after(node.id, node_input, node_output)
                except Exception as exc:
                    self.logger.warning(f"Node '{node.id}' cache store errored; not cached: {exc}")
        return node_output, record


__all__ = ["ActionRunner"]

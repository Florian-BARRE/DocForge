# ====== Code Summary ======
# PipelineRunner — the worker's execution heart: turn a collection's pipeline blob + one source
# document into the run's delivery. It builds and validates the graph (fail-fast, before any
# spend), hands the engine a FRESH run input per job (never reuse: enrich_apply returns the very
# ir object the run input carried), and enforces the OUTPUT CONTRACT: an ingestion pipeline must
# deliver a RunBundle. Persistence lives elsewhere (the translator) — the runner only runs.

# ====== Standard Library Imports ======
import asyncio

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    ActionNode,
    ForEach,
    Group,
    NodeExecutionRecord,
    NodeStatus,
)
from shared_libs.pipelines.build import GroupNodeBlob, PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine, ProgressCallback
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import CollectionContract, RunBundle, SourceDocument

# Overall wall-clock cap for the whole preflight sweep — a safety net above each probe's own
# short timeout + retry (they run concurrently, so this bounds the sweep regardless of node count).
_PREFLIGHT_TIMEOUT_SECONDS = 20.0


class PipelineRunError(Exception):
    """Raised when a run cannot start (invalid graph) or did not deliver (failed / no bundle)."""


class PipelineRunner(LoggerClass):
    """
    Executes one ingestion run: blob in, RunBundle + execution record out.

    Stateless across runs — safe to share across concurrent jobs (the engine keeps all
    run-scoped state in its RunContext).
    """

    def __init__(self) -> None:
        LoggerClass.__init__(self)
        self._builder = PipelineBuilder()
        self._validator = GraphValidator()
        self._engine = FlowEngine(trace_payloads=False)

    @staticmethod
    def __failed_node_reason(record: NodeExecutionRecord) -> str | None:
        """
        Find the deepest node that actually raised and format it for the job error.

        A group's own ``error`` is None — the fatal cause is a FAILED leaf nested in its
        children. Walking depth-first turns the opaque "see the execution record" into the
        actual node and message (e.g. "parse (docling): ModuleNotFoundError: ...").

        Args:
            record (NodeExecutionRecord): The run's root execution record.

        Returns:
            str | None: "node_id (kind): ErrorType: message" for the failing node, or None
            when no FAILED leaf carries an error.
        """
        # 1. Depth-first — a nested failure is more specific than the group above it.
        for child in record.children:
            reason = PipelineRunner.__failed_node_reason(child)
            if reason:
                return reason
        # 2. This node is the culprit only if it FAILED with a captured error.
        if record.status == NodeStatus.FAILED and record.error is not None:
            return f"{record.node_id} ({record.kind}): {record.error.error_type}: {record.error.message}"
        return None

    @staticmethod
    def __collect_action_nodes(group: Group) -> list[ActionNode]:
        """
        Collect every ActionNode in the built graph, recursing into groups and ForEach bodies.

        Walks the SAME node taxonomy the engine dispatches on, so a provider nested inside a
        ForEach (e.g. a per-page VLM) is preflighted too — otherwise its unreachable endpoint
        would only surface mid-run.

        Args:
            group (Group): The built pipeline (or a nested sub-graph).

        Returns:
            list[ActionNode]: Every action leaf reachable from this group.
        """
        nodes: list[ActionNode] = []
        for child in group.children:
            if isinstance(child, Group):
                nodes.extend(PipelineRunner.__collect_action_nodes(child))
            elif isinstance(child, ForEach):
                nodes.extend(PipelineRunner.__collect_action_nodes(child.body))
            elif isinstance(child, ActionNode):
                nodes.append(child)
        return nodes

    async def __preflight(self, group: Group) -> None:
        """
        Run every node's preflight() concurrently, BEFORE the first spend — fail fast if any is unreachable.

        A node whose preflight is the default no-op costs nothing. Provider overrides probe their
        endpoint's reachability + credentials; any failure (or the overall timeout) aborts the run
        before a single byte is read or stored.

        Args:
            group (Group): The built + validated pipeline graph.

        Raises:
            PipelineRunError: One or more nodes failed preflight (named with their reason), or the
                sweep exceeded its overall timeout.
        """
        # 1. Every action leaf, including those nested in groups and ForEach bodies.
        nodes = self.__collect_action_nodes(group)
        if not nodes:
            return

        async def probe(node: ActionNode) -> str | None:
            """Run one node's preflight, turning any failure into a named reason string."""
            try:
                await node.preflight()
                return None
            except Exception as exc:  # noqa: BLE001 — any failure aborts the run, named below.
                return f"{node.id} ({node.KIND}): {exc}"

        # 2. All probes concurrently, under one overall cap (a hung probe cannot stall the run).
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*(probe(node) for node in nodes)),
                timeout=_PREFLIGHT_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise PipelineRunError(
                f"preflight sweep exceeded {_PREFLIGHT_TIMEOUT_SECONDS:.0f}s — endpoint(s) too slow "
                f"to reach before spend"
            ) from exc

        # 3. Any failure aborts BEFORE spend, naming each culprit node + reason.
        failures = [reason for reason in results if reason]
        if failures:
            raise PipelineRunError(
                f"preflight failed for {len(failures)} node(s) before any spend: "
                + "; ".join(failures)
            )

    async def run(
        self,
        blob: GroupNodeBlob | dict,
        source: SourceDocument,
        contract: CollectionContract,
        timeout_seconds: float,
        progress_callback: ProgressCallback | None = None,
        preflight_enabled: bool = True,
    ) -> tuple[RunBundle, NodeExecutionRecord]:
        """
        Execute one ingestion run end to end.

        Args:
            blob (GroupNodeBlob | dict): The collection's pipeline blob.
            source (SourceDocument): The uploaded document (bytes + declared metadata).
            contract (CollectionContract): The collection's contract.
            timeout_seconds (float): Wall-clock cap for the whole run.
            progress_callback (ProgressCallback | None): Live per-node progress (job status).
            preflight_enabled (bool): When True (default), sweep every node's preflight() after
                build/validate and BEFORE the first spend — a provider pointed at an unreachable
                endpoint fails fast, having stored nothing.

        Returns:
            tuple[RunBundle, NodeExecutionRecord]: The delivery and the full execution trace.

        Raises:
            PipelineRunError: Invalid graph, failed run, or a final output that is not the
                RunBundle contract — each with a precise message.
        """
        # 1. Build + validate BEFORE any spend — a broken collection blob never runs.
        group = self._builder.build(blob)
        issues = self._validator.validate(group)
        if issues:
            details = "; ".join(
                f"[{issue.code}] {issue.location}: {issue.message}" for issue in issues
            )
            raise PipelineRunError(f"invalid pipeline graph ({len(issues)} issue(s)): {details}")

        # 2. Preflight reachability BEFORE any spend — a wrong/unreachable endpoint fails fast here,
        #    having read/stored nothing (the last honest gap the structural validator cannot cover).
        if preflight_enabled:
            await self.__preflight(group)

        # 3. A FRESH run input per job — the run MUTATES what it carries (the ir, by design).
        run_input = {"source": source, "contract": contract}

        # 4. Execute under the wall-clock cap.
        self.logger.info(f"Running ingestion pipeline '{group.id}' for '{source.filename}'")
        output, record = await self._engine.execute(
            group, run_input, timeout_seconds=timeout_seconds, progress_callback=progress_callback
        )

        # 4. A failed run surfaces the engine's error, verbatim.
        if output is None:
            reason = self.__failed_node_reason(record) or (
                record.error.message if record.error else "see the execution record"
            )
            raise PipelineRunError(f"pipeline run failed: {reason}")

        # 5. The OUTPUT CONTRACT: the final node must deliver the RunBundle.
        bundle = getattr(output, "bundle", None)
        if not isinstance(bundle, RunBundle):
            raise PipelineRunError(
                f"the pipeline's final node produced '{type(output).__name__}' — an ingestion "
                f"pipeline must end on a deliver/bundle node producing a RunBundle"
            )
        vector_sets = len(bundle.embeddings.items) if bundle.embeddings else 0
        self.logger.info(
            f"Run delivered: {len(bundle.chunks)} chunk(s), "
            f"{vector_sets} vector set(s), {bundle.ingest.page_count} page(s)"
        )
        return bundle, record


__all__ = ["PipelineRunner", "PipelineRunError"]

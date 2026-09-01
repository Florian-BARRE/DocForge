# ====== Code Summary ======
# PipelineRunner — the worker's execution heart: turn a collection's pipeline blob + one source
# document into the run's delivery. It builds and validates the graph (fail-fast, before any
# spend), hands the engine a FRESH run input per job (never reuse: enrich_apply returns the very
# ir object the run input carried), and enforces the OUTPUT CONTRACT: an ingestion pipeline must
# deliver a RunBundle. Persistence lives elsewhere (the translator) — the runner only runs.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    Group,
    NodeExecutionRecord,
)
from shared_libs.pipelines.build import GroupNodeBlob, PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine, ProgressCallback
from shared_libs.pipelines.reachability import ProbeStatus, ReachabilitySweep
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import CollectionContract, RunBundle, SourceDocument

# ====== Local Project Imports ======
from .breadcrumb import FailureBreadcrumb

# The side stamped on the worker's ingest preflight results (it only sweeps the ingest graph).
_INGEST_SIDE = "ingest"

# Probe outcomes that do NOT fail the run: the endpoint answered (ok) or there was nothing to
# reach (a local leaf with no endpoint). Anything else aborts before the first spend.
_PASSING_STATUSES = frozenset({ProbeStatus.OK, ProbeStatus.SKIPPED})


class PipelineRunError(Exception):
    """Raised when a run cannot start (invalid graph) or did not deliver (failed / no bundle).

    Carries the structured ``breadcrumb`` when the failure came from a specific node, so the worker
    persists WHERE it died (node / kind / item / error type) alongside the free-text message.
    """

    def __init__(self, message: str, breadcrumb: FailureBreadcrumb | None = None) -> None:
        """
        Args:
            message (str): The human-readable failure reason.
            breadcrumb (FailureBreadcrumb | None): The structured failing-node breadcrumb, when the
                failure was located to a node (None for pre-run errors like an invalid graph).
        """
        super().__init__(message)
        self.breadcrumb = breadcrumb


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
        self._sweep = ReachabilitySweep()

    async def __preflight(self, group: Group) -> None:
        """
        Sweep every provider leaf's reachability BEFORE the first spend — fail fast if any is down.

        Delegates the walk + probing to the shared ReachabilitySweep (the same public seam the app's
        on-demand collection-health endpoint uses), then applies the worker's own policy: any leaf
        whose endpoint is unreachable or whose credentials are rejected aborts the run before a
        single byte is read or stored. Local leaves (no endpoint) come back ``skipped`` and pass.

        Args:
            group (Group): The built + validated pipeline graph.

        Raises:
            PipelineRunError: One or more provider leaves failed preflight (named with their reason).
        """
        # 1. Structured per-leaf outcomes from the shared sweep (probes run concurrently, capped).
        results = await self._sweep.sweep(group, _INGEST_SIDE)

        # 2. The worker's policy: anything that is not ok/skipped aborts BEFORE spend, named.
        failures = [
            f"{result.node_id} ({result.kind}): {result.detail}"
            for result in results
            if result.status not in _PASSING_STATUSES
        ]
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

        # 4. A failed run surfaces the engine's error, verbatim — and the structured breadcrumb (the
        #    deepest failing node + its fan-out item) so the worker persists WHERE it died, not just why.
        if output is None:
            breadcrumb = FailureBreadcrumb.from_record(record)
            reason = (
                breadcrumb.reason
                if breadcrumb is not None
                else (record.error.message if record.error else "see the execution record")
            )
            raise PipelineRunError(f"pipeline run failed: {reason}", breadcrumb=breadcrumb)

        # 5. The OUTPUT CONTRACT: the final node must deliver the RunBundle.
        bundle = getattr(output, "bundle", None)
        if not isinstance(bundle, RunBundle):
            raise PipelineRunError(
                f"the pipeline's final node produced '{type(output).__name__}' — an ingestion "
                f"pipeline must end on a deliver/bundle node producing a RunBundle"
            )

        # 6. The DELIVERY CONTRACT: a run that chunked NOTHING delivered nothing retrievable. Causes
        #    span a mis-wired chunker (chunks slot unbound), an empty/failed parse, every page failing
        #    OCR, AND a genuinely content-free input (an image-only PDF with OCR off, a blank scanned
        #    page). The chunker treats the last case as a warn-and-continue, but at the job edge all of
        #    them are the same user-visible outcome: a green job whose document is INVISIBLE to search
        #    (silent data loss). Surface it as a loud, actionable failure instead — an operator can
        #    then enable OCR / fix the source and reingest. Deliberately keyed on chunks, NOT vectors:
        #    an embed stage legitimately yields zero vectors for an all-furniture document (embed keeps
        #    only enabled/searchable chunks), and a pipeline with no embed stage yields none by design
        #    (Postgres-complete) — neither is a failure, and distinguishing them from a mis-wire would
        #    duplicate the node's embed policy into the worker. Zero CHUNKS has no retrievable outcome.
        if not bundle.chunks:
            raise PipelineRunError(
                "the pipeline delivered zero chunks — nothing retrievable was produced "
                "(an empty or failed parse, every page failing OCR, a document with no extractable "
                "text content, or an unbound chunker slot)"
            )

        vector_sets = len(bundle.embeddings.items) if bundle.embeddings else 0
        self.logger.info(
            f"Run delivered: {len(bundle.chunks)} chunk(s), "
            f"{vector_sets} vector set(s), {bundle.ingest.page_count} page(s)"
        )
        return bundle, record


__all__ = ["PipelineRunner", "PipelineRunError"]

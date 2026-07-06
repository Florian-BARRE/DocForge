# ====== Code Summary ======
# PipelineRunner — the worker's execution heart: turn a collection's pipeline blob + one source
# document into the run's delivery. It builds and validates the graph (fail-fast, before any
# spend), hands the engine a FRESH run input per job (never reuse: enrich_apply returns the very
# ir object the run input carried), and enforces the OUTPUT CONTRACT: an ingestion pipeline must
# deliver a RunBundle. Persistence lives elsewhere (the translator) — the runner only runs.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord
from shared_libs.pipelines.build import GroupNodeBlob, PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine, ProgressCallback
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import CollectionContract, RunBundle, SourceDocument


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
        self._engine = FlowEngine()

    async def run(
        self,
        blob: GroupNodeBlob | dict,
        source: SourceDocument,
        contract: CollectionContract,
        timeout_seconds: float,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[RunBundle, NodeExecutionRecord]:
        """
        Execute one ingestion run end to end.

        Args:
            blob (GroupNodeBlob | dict): The collection's pipeline blob.
            source (SourceDocument): The uploaded document (bytes + declared metadata).
            contract (CollectionContract): The collection's contract.
            timeout_seconds (float): Wall-clock cap for the whole run.
            progress_callback (ProgressCallback | None): Live per-node progress (job status).

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
            details = "; ".join(f"[{issue.code}] {issue.location}: {issue.message}" for issue in issues)
            raise PipelineRunError(f"invalid pipeline graph ({len(issues)} issue(s)): {details}")

        # 2. A FRESH run input per job — the run MUTATES what it carries (the ir, by design).
        run_input = {"source": source, "contract": contract}

        # 3. Execute under the wall-clock cap.
        self.logger.info(f"Running ingestion pipeline '{group.id}' for '{source.filename}'")
        output, record = await self._engine.execute(
            group, run_input, timeout_seconds=timeout_seconds, progress_callback=progress_callback
        )

        # 4. A failed run surfaces the engine's error, verbatim.
        if output is None:
            reason = record.error.message if record.error else "see the execution record"
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

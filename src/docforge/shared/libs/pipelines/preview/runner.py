# ====== Code Summary ======
# PreviewRunner — the SHARED execution heart of an ingestion DRY-RUN, reused by BOTH preview paths:
# the app's inline fast-lane (PreviewService) AND the worker preview job (which has docling + every
# heavy dep the app image lacks, so it covers the general case). It reuses the engine/builder/validator
# verbatim — build + structurally validate BEFORE any spend (a broken blob becomes a typed
# PreviewGraphError → 422 on the inline path / ok=false DATA on the worker path, never an engine crash),
# then FlowEngine.execute on ONE {source, contract} run input under a short wall-clock cap. It does NOT
# persist anything (the worker's RunTranslator is never invoked) and it does NOT preflight (a down
# provider simply surfaces as a failed node in the returned trace — exactly what a dry-run is for). A
# run that FAILED is DATA, not an exception: the partial RunBundle is None and the partial execution
# record is returned so the caller can show WHERE it died. The engine stays pure — nodes do zero I/O.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord
from shared_libs.pipelines.build import GroupNodeBlob, PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine, TraceLevel
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models import CollectionContract, RunBundle, SourceDocument

# ====== Local Project Imports ======
from .errors import PreviewGraphError


class PreviewRunner(LoggerClass):
    """
    Executes one ingestion dry-run: blob + source + contract in, (RunBundle | None, record) out.

    Stateless across runs — safe to reuse across concurrent requests (the engine keeps all run-scoped
    state in its own RunContext). Persists NOTHING: it is the pure runner with the worker's
    persistence/translate boundary simply not attached.
    """

    def __init__(self) -> None:
        LoggerClass.__init__(self)
        self._builder = PipelineBuilder()
        self._validator = GraphValidator()
        # A dry-run captures the full node tree (status/score/usage/error are lifted onto the record at
        # EVERY trace level) but needs no heavy input/output payloads — OFF is the cheapest level that
        # still yields the tree the preview projects, exactly like the inline search runner.
        self._engine = FlowEngine(trace_level=TraceLevel.OFF)

    def __build_validated(self, blob: GroupNodeBlob | dict) -> object:
        """
        Build + structurally validate a graph BEFORE any spend — a broken blob is a typed 422.

        Args:
            blob (GroupNodeBlob | dict): The ingestion pipeline blob to dry-run.

        Returns:
            Group: The built, validated graph.

        Raises:
            PreviewGraphError: The blob does not build or does not structurally validate.
        """
        group = self._builder.build(blob)
        issues = self._validator.validate(group)
        if issues:
            details = "; ".join(
                f"[{issue.code}] {issue.location}: {issue.message}" for issue in issues
            )
            raise PreviewGraphError(f"invalid pipeline graph ({len(issues)} issue(s)): {details}")
        return group

    async def run(
        self,
        blob: GroupNodeBlob | dict,
        source: SourceDocument,
        contract: CollectionContract,
        timeout_seconds: float,
    ) -> tuple[RunBundle | None, NodeExecutionRecord]:
        """
        Execute one ingestion dry-run inline and return its (delivery or None) plus the execution trace.

        Args:
            blob (GroupNodeBlob | dict): The pipeline blob to dry-run (a candidate or the stored one).
            source (SourceDocument): The source to run on (uploaded bytes or a rehydrated document).
            contract (CollectionContract): The collection's contract (the same the worker binds).
            timeout_seconds (float): Wall-clock cap for the whole inline run (the interactive guardrail).

        Returns:
            tuple[RunBundle | None, NodeExecutionRecord]: the delivery (None when a node failed) and the
                full execution record (the partial tree up to the failing node on a failed run).

        Raises:
            PreviewGraphError: The blob is unbuildable/invalid, or its final output is not a RunBundle
                (the blob is not an ingestion pipeline).
        """
        # 1. Build + validate BEFORE any spend — an invalid blob is a typed error, never an engine crash.
        group = self.__build_validated(blob)

        # 2. A FRESH run input per run — the run MUTATES the ir it carries, by design.
        run_input = {"source": source, "contract": contract}

        # 3. Execute inline under the wall-clock cap. A failed node returns output=None + the partial
        #    record (the engine does not raise on a FAIL-policy node) — that is DATA the projector shows.
        self.logger.info(f"Dry-running ingestion pipeline '{group.id}' for '{source.filename}'")
        output, record = await self._engine.execute(
            group, run_input, timeout_seconds=timeout_seconds
        )

        # 4. No delivery → a failed/timed-out run: hand back the partial tree, let the projector report it.
        if output is None:
            return None, record

        # 5. The OUTPUT CONTRACT: a genuine ingestion pipeline must deliver a RunBundle. A blob whose
        #    final node produces anything else is not an ingestion graph — a 422, not a run outcome.
        bundle = getattr(output, "bundle", None)
        if not isinstance(bundle, RunBundle):
            raise PreviewGraphError(
                f"the pipeline's final node produced '{type(output).__name__}' — an ingestion "
                f"pipeline must end on a deliver/bundle node producing a RunBundle"
            )
        return bundle, record


__all__ = ["PreviewRunner"]

# ====== Code Summary ======
# SearchRunner — the app-side execution heart of the search pipeline, the search analog of the
# worker's PipelineRunner. Search runs INLINE in the API request (sub-second, no arq), so this
# lives app-side. It builds + validates the graph (fail-fast, a broken blob becomes a typed error,
# never an engine crash), binds the read-only CollectionReadPort onto the port-backed nodes — the
# engine does NOT bind, so the runner walks the built group's children and injects the capability
# BEFORE execution — runs FlowEngine.execute with the {query, filters, contract} run-input, and
# enforces the OUTPUT CONTRACT: a search pipeline must deliver a SearchResult. The engine, builder
# and validator are reused verbatim.

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
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.search import COLLECTION_READ_CAPABILITY, CollectionReadPort
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.public_models.search import SearchResult

# The error_type the encode node stamps when NO query vector axis could be produced (the shared
# embedder is saturated) — the runner keys the retryable "unavailable" mapping off it, never a
# string match on the message.
_ENCODE_UNAVAILABLE_ERROR = "QueryEncodeError"

# The error_type the engine stamps on the record when the whole run exceeds its wall-clock cap.
_TIMEOUT_ERROR = "TimeoutError"


class SearchRunError(Exception):
    """Raised when a search run cannot start (invalid graph) or did not deliver a SearchResult.

    This is the "the stored graph is wrong" failure — the router maps it to a 422. Its two
    subclasses below are the TRANSIENT, retryable failures a healthy graph can still hit under load;
    the router maps those to 503/504 instead, so a busy embedder never reads as an invalid blob.
    """


class SearchRunTimeout(SearchRunError):
    """Raised when the run exceeded its wall-clock cap (the embedder/provider is stuck).

    A retryable timeout, NOT an invalid graph — the router maps it to a 504.
    """


class SearchUnavailableError(SearchRunError):
    """Raised when the run failed because the query could not be encoded (the embedder is busy).

    A retryable outage of a healthy graph, NOT an invalid blob — the router maps it to a 503.
    """


class SearchRunner(LoggerClass):
    """
    Executes one search run: blob + run-input + read port in, SearchResult out.

    Stateless across runs — safe to reuse across concurrent requests (the engine keeps all
    run-scoped state in its own RunContext; the read port is bound per-run onto a freshly built
    graph, never shared between runs).
    """

    def __init__(self) -> None:
        LoggerClass.__init__(self)
        self._builder = PipelineBuilder()
        self._validator = GraphValidator()
        self._engine = FlowEngine(trace_payloads=False)

    @staticmethod
    def __failed_node_reason(record: NodeExecutionRecord) -> str | None:
        """
        Find the deepest node that actually raised and format it for the run error.

        A group's own ``error`` is None — the fatal cause is a FAILED leaf nested in its children.
        Walking depth-first turns the opaque "see the execution record" into the actual node and
        message (e.g. "retrieve (hybrid): RuntimeError: ...").

        Args:
            record (NodeExecutionRecord): The run's root execution record.

        Returns:
            str | None: "node_id (kind): ErrorType: message" for the failing node, or None.
        """
        # 1. Depth-first — a nested failure is more specific than the group above it.
        for child in record.children:
            reason = SearchRunner.__failed_node_reason(child)
            if reason:
                return reason
        # 2. This node is the culprit only if it FAILED with a captured error.
        if record.status == NodeStatus.FAILED and record.error is not None:
            return f"{record.node_id} ({record.kind}): {record.error.error_type}: {record.error.message}"
        return None

    @staticmethod
    def __failed_error_type(record: NodeExecutionRecord) -> str | None:
        """
        Find the error_type of the deepest node that actually raised.

        Mirrors __failed_node_reason but returns the bare error_type so the runner can key its
        failure MAPPING off it (e.g. a QueryEncodeError → retryable "unavailable") without parsing
        a formatted message.

        Args:
            record (NodeExecutionRecord): The run's root execution record.

        Returns:
            str | None: The failing leaf's error_type, or None when nothing captured an error.
        """
        for child in record.children:
            error_type = SearchRunner.__failed_error_type(child)
            if error_type:
                return error_type
        if record.status == NodeStatus.FAILED and record.error is not None:
            return record.error.error_type
        return None

    def __bind_read_port(self, group: Group, read_port: CollectionReadPort) -> None:
        """
        Inject the read port into every action node of the built graph (recursively).

        The engine never calls bind(); the runner does it here, after build and before execute.
        Binding every action node (not just the port-backed ones) is harmless — a node that does
        not read a store simply ignores the capability — and keeps the walk trivial. The walk must
        cover the SAME node taxonomy the engine dispatches on: leaves, nested groups AND ForEach
        bodies — a port-backed node inside a ForEach (e.g. a per-sub-query retrieve) would otherwise
        run unbound and raise at first read.

        Args:
            group (Group): The built search graph.
            read_port (CollectionReadPort): The capability to inject.
        """
        # 1. Depth-first: bind leaves, recurse into nested groups and ForEach bodies (both Groups).
        for child in group.children:
            if isinstance(child, Group):
                self.__bind_read_port(child, read_port)
            elif isinstance(child, ForEach):
                self.__bind_read_port(child.body, read_port)
            elif isinstance(child, ActionNode):
                child.bind({COLLECTION_READ_CAPABILITY: read_port})

    async def run(
        self,
        blob: GroupNodeBlob | dict,
        run_input: dict,
        read_port: CollectionReadPort,
        timeout_seconds: float | None = None,
    ) -> SearchResult:
        """
        Execute one search run end to end and return its terminal SearchResult.

        Args:
            blob (GroupNodeBlob | dict): The search pipeline blob (the stock default today).
            run_input (dict): The run input addressable by FromRunInput — ``{query, filters,
                contract}``.
            read_port (CollectionReadPort): The read-only capability bound onto the port-backed
                nodes (the exclusion invariant lives inside it).
            timeout_seconds (float | None): Wall-clock cap for the whole run (None = no cap).

        Returns:
            SearchResult: The ranked answer to the query.

        Raises:
            SearchRunError: Invalid graph, failed run, or a final output that is not the
                SearchResult contract — each with a precise message.
        """
        # 1. Build + validate BEFORE any spend — a broken blob is a typed error, never a crash.
        group = self._builder.build(blob)
        issues = self._validator.validate(group)
        if issues:
            details = "; ".join(
                f"[{issue.code}] {issue.location}: {issue.message}" for issue in issues
            )
            raise SearchRunError(f"invalid search graph ({len(issues)} issue(s)): {details}")

        # 2. Bind the read port onto the port-backed nodes — the engine does NOT bind.
        self.__bind_read_port(group, read_port)

        # 3. Execute inline under the wall-clock cap.
        self.logger.info(f"Running search pipeline '{group.id}'")
        output, record = await self._engine.execute(
            group, run_input, timeout_seconds=timeout_seconds
        )

        # 4. A failed run — DISTINGUISH the transient, retryable failures of a healthy graph from a
        #    genuine "the graph is wrong" failure, so the router never mislabels a busy embedder as
        #    an invalid blob.
        if output is None:
            reason = self.__failed_node_reason(record) or (
                record.error.message if record.error else "see the execution record"
            )
            error_type = self.__failed_error_type(record) or (
                record.error.error_type if record.error else None
            )
            # 4a. The whole run blew the wall-clock cap — the provider is stuck. Retryable 504.
            if error_type == _TIMEOUT_ERROR:
                raise SearchRunTimeout(f"search run timed out: {reason}")
            # 4b. The query could not be encoded on any axis — the embedder is busy. Retryable 503.
            if error_type == _ENCODE_UNAVAILABLE_ERROR:
                raise SearchUnavailableError(f"search temporarily unavailable: {reason}")
            # 4c. Anything else is a genuine run failure of the graph itself.
            raise SearchRunError(f"search run failed: {reason}")

        # 5. The OUTPUT CONTRACT: the final node must deliver a SearchResult.
        result = getattr(output, "result", None)
        if not isinstance(result, SearchResult):
            raise SearchRunError(
                f"the pipeline's final node produced '{type(output).__name__}' — a search "
                f"pipeline must end on a deliver/hits node producing a SearchResult"
            )
        self.logger.info(f"Search delivered {len(result.hits)} hit(s)")
        return result


__all__ = ["SearchRunner", "SearchRunError", "SearchRunTimeout", "SearchUnavailableError"]

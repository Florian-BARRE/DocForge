# ====== Code Summary ======
# PreviewProjector — PURE projection of an inline dry-run's in-memory result (RunBundle + execution
# record) into the bounded PreviewResponse. It reuses the SAME shared machinery the real paths use:
# UsageSummer prices the run's ACTUAL spend (the worker/search meter), and ExecutionTreeFlattener
# produces the materialized-path trace (the worker's persist path). It never touches a store — it only
# reads the objects the runner already built, clips chunk text to the preview ceiling, and summarizes
# the IR. A failed run (bundle None) projects ok=false with the partial trace + the deepest failing node.

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord, NodeStatus
from shared_libs.pipelines.ingest.estimate import RateTable
from shared_libs.pipelines.usage import UsageSummer
from shared_libs.public_models import RunBundle
from shared_libs.services.db.postgresql.apis.execution_tree import ExecutionTreeFlattener

# ====== Local Project Imports ======
from .models import (
    PreviewChunk,
    PreviewCost,
    PreviewIrSummary,
    PreviewResponse,
    PreviewTraceNode,
)


class PreviewProjector:
    """Static helper: (RunBundle | None, execution record) → the bounded PreviewResponse."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("PreviewProjector is a static-only class and cannot be instantiated.")

    @classmethod
    def project(
        cls,
        bundle: RunBundle | None,
        record: NodeExecutionRecord,
        rates: RateTable,
        source_filename: str,
        max_chunks: int,
        text_max_chars: int,
    ) -> PreviewResponse:
        """
        Project the in-memory dry-run result into the bounded preview report.

        Args:
            bundle (RunBundle | None): The delivery, or None when a node failed.
            record (NodeExecutionRecord): The run's execution record (full on success, partial on fail).
            rates (RateTable): The collection's effective rates — the spend is priced identically to a
                real run.
            source_filename (str): The previewed source's filename.
            max_chunks (int): How many chunks to return at most (the rest are summarized by the count).
            text_max_chars (int): Per-chunk text/context truncation ceiling.

        Returns:
            PreviewResponse: The bounded dry-run report (ok=false + trace when the run failed).
        """
        # 1. Cost + trace are available whether or not a bundle was delivered (the record always exists).
        prompt, completion, cost_usd, priced = UsageSummer.summarize(record, rates)
        cost = PreviewCost(
            prompt_tokens=prompt,
            completion_tokens=completion,
            cost_usd=cost_usd,
            priced_call_count=priced,
        )
        trace = cls.__project_trace(record)

        # 2. A failed run: no delivery — report where it died (deepest failing leaf), empty preview body.
        if bundle is None:
            node_id, node_kind, reason = cls.__deepest_failure(record)
            return PreviewResponse(
                ok=False,
                source_filename=source_filename,
                ir=None,
                chunk_count=0,
                chunks=[],
                chunks_truncated=False,
                vector_set_count=0,
                cost=cost,
                trace=trace,
                warnings=[],
                failed_node_id=node_id,
                failed_node_kind=node_kind,
                error=reason or "pipeline run failed (see the execution trace)",
            )

        # 3. A delivered run: summarize the IR, clip the first N chunks, flag a zero-chunk warning.
        chunk_count = len(bundle.chunks)
        chunks = [
            cls.__project_chunk(chunk, text_max_chars) for chunk in bundle.chunks[:max_chunks]
        ]
        vector_sets = len(bundle.embeddings.items) if bundle.embeddings else 0
        warnings: list[str] = []
        if chunk_count == 0:
            warnings.append(
                "The pipeline ran to completion but produced 0 chunks — nothing retrievable would be "
                "created (the document may be empty or image-only with no extractable text)."
            )
        return PreviewResponse(
            ok=True,
            source_filename=source_filename,
            ir=cls.__project_ir(bundle),
            chunk_count=chunk_count,
            chunks=chunks,
            chunks_truncated=chunk_count > len(chunks),
            vector_set_count=vector_sets,
            cost=cost,
            trace=trace,
            warnings=warnings,
        )

    @staticmethod
    def failed_precheck(source_filename: str, error: str) -> PreviewResponse:
        """
        Build an ok=false report for a failure that happened BEFORE any node ran (no execution tree).

        Used by the worker preview job: a bad/unbuildable candidate blob or an unmigratable stored
        blob is DATA here (the inline path raises a 422, but a polled worker job cannot), so the run
        never starts and there is no record/bundle to project — only the reason. The app's inline path
        keeps raising the typed error; this keeps the async path's contract "a failed preview is always
        a PreviewResponse with ok=false, never a 500".

        Args:
            source_filename (str): The previewed source's filename.
            error (str): The human-readable failure reason (bad blob / unmigratable / bad input).

        Returns:
            PreviewResponse: An ok=false report with an empty body, zero cost and an empty trace.
        """
        return PreviewResponse(
            ok=False,
            source_filename=source_filename,
            ir=None,
            chunk_count=0,
            chunks=[],
            chunks_truncated=False,
            vector_set_count=0,
            cost=PreviewCost(
                prompt_tokens=0, completion_tokens=0, cost_usd=None, priced_call_count=0
            ),
            trace=[],
            warnings=[],
            error=error,
        )

    @staticmethod
    def __project_ir(bundle: RunBundle) -> PreviewIrSummary:
        """Summarize the enriched IR + intake facts into the compact preview shape."""
        ir = bundle.ir
        type_counts: dict[str, int] = {}
        for block in ir.blocks:
            key = str(block.block_type)
            type_counts[key] = type_counts.get(key, 0) + 1
        return PreviewIrSummary(
            title=ir.title,
            language=ir.language,
            page_count=bundle.ingest.page_count,
            source_format=bundle.ingest.source_format,
            file_size=len(bundle.ingest.source_content) if bundle.ingest.source_content else 0,
            source_hash=bundle.ingest.source_hash,
            block_count=len(ir.blocks),
            block_type_counts=type_counts,
            figure_count=len(ir.figure_blocks),
        )

    @staticmethod
    def __project_chunk(chunk: object, text_max_chars: int) -> PreviewChunk:
        """Project one chunk, clipping its text/context to the preview ceiling."""
        text = chunk.text  # type: ignore[attr-defined]
        return PreviewChunk(
            chunk_id=chunk.chunk_id,  # type: ignore[attr-defined]
            ordinal=chunk.ordinal,  # type: ignore[attr-defined]
            role=str(chunk.role),  # type: ignore[attr-defined]
            heading_path=list(chunk.heading_path),  # type: ignore[attr-defined]
            token_count=chunk.token_count,  # type: ignore[attr-defined]
            page_start=chunk.page_start,  # type: ignore[attr-defined]
            page_end=chunk.page_end,  # type: ignore[attr-defined]
            text=text[:text_max_chars],
            text_truncated=len(text) > text_max_chars,
            context=chunk.context[:text_max_chars],  # type: ignore[attr-defined]
            generated_meta=dict(chunk.generated_meta),  # type: ignore[attr-defined]
        )

    @classmethod
    def __project_trace(cls, record: NodeExecutionRecord) -> list[PreviewTraceNode]:
        """Flatten the execution record into materialized-path trace rows (reusing the worker's flattener)."""
        return [
            PreviewTraceNode(
                node_id=flat.record.node_id,
                kind=flat.record.kind,
                status=str(flat.record.status),
                duration_ms=flat.record.duration_ms,
                depth=flat.depth,
                node_path=flat.node_path,
                parent_path=flat.parent_path,
                item_index=flat.item_index,
                score=flat.record.score,
                error_type=flat.record.error.error_type if flat.record.error else None,
                error_message=flat.record.error.message if flat.record.error else None,
            )
            for flat in ExecutionTreeFlattener.flatten(record)
        ]

    @classmethod
    def __deepest_failure(
        cls, record: NodeExecutionRecord
    ) -> tuple[str | None, str | None, str | None]:
        """
        Find the deepest node that actually raised — the real cause behind an opaque group failure.

        Returns:
            tuple[str | None, str | None, str | None]: (node_id, kind, "ErrorType: message") of the
                deepest failing leaf, or (None, None, None) when nothing captured an error.
        """
        # 1. Depth-first — a nested failure is more specific than the group above it.
        for child in record.children:
            found = cls.__deepest_failure(child)
            if found[0] is not None:
                return found
        # 2. This node is the culprit only if it FAILED with a captured error.
        if record.status == NodeStatus.FAILED and record.error is not None:
            return (
                record.node_id,
                record.kind,
                f"{record.error.error_type}: {record.error.message}",
            )
        return None, None, None


__all__ = ["PreviewProjector"]

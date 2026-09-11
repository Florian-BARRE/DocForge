# ====== Code Summary ======
# Response models for the pipeline dry-run preview endpoint, mirrored field-for-field from
# app/backend/libs/preview/models.py. A preview runs the ingestion graph inline on ONE document and
# persists NOTHING; the response is a bounded report — an IR summary, the first N chunks (text
# truncated), the run's ACTUAL metered cost, the full execution trace, and any warnings. A failed node
# is DATA here (ok=false + the failing node + the partial trace), never an error response.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class PreviewIrSummary(BaseModel):
    """A compact summary of the canonical IR a dry-run produced (the full IR is never returned)."""

    title: str = Field(description="Parser-extracted document title (empty when unavailable).")
    language: str = Field(description="Dominant ISO 639-1 language code (empty when undetected).")
    page_count: int = Field(description="Total page count of the parsed document.")
    source_format: str = Field(
        description="Detected source format token (pdf, docx, html, txt, …)."
    )
    file_size: int = Field(description="Size of the original source bytes.")
    source_hash: str = Field(description="Content-addressing hash of the original bytes.")
    block_count: int = Field(description="Total number of IR blocks in reading order.")
    block_type_counts: dict[str, int] = Field(
        description="Count of blocks per block type (e.g. {'paragraph': 42, 'figure': 3})."
    )
    figure_count: int = Field(description="Number of FIGURE blocks in the IR.")


class PreviewChunk(BaseModel):
    """One previewed retrieval unit — text truncated to the preview ceiling, never the full chunk."""

    chunk_id: str = Field(description="Stable chunk identifier within the document.")
    ordinal: int = Field(description="Reading-order position among the document's chunks.")
    role: str = Field(description="Structural role (body / header-footer / toc / boilerplate).")
    heading_path: list[str] = Field(description="Section ancestry, top-down.")
    token_count: int = Field(description="Token count of the full (untruncated) chunk text.")
    page_start: int = Field(description="First source page covered (0-indexed).")
    page_end: int = Field(description="Last source page covered (0-indexed).")
    text: str = Field(description="The raw chunk text, truncated to the preview character ceiling.")
    text_truncated: bool = Field(description="True when the raw text was clipped for the preview.")
    context: str = Field(description="Retrieval context accumulated by contextualize (truncated).")
    generated_meta: dict[str, Any] = Field(
        description="Chunk-scope generated metadata (per contract)."
    )


class PreviewCost(BaseModel):
    """The dry-run's ACTUAL metered spend on this one document, priced against the collection's rates."""

    prompt_tokens: int = Field(description="Total input tokens billed across the run's paid calls.")
    completion_tokens: int = Field(
        description="Total output tokens billed across the run's paid calls."
    )
    cost_usd: float | None = Field(
        description="Total USD cost, or null when no paid leaf had a known rate (tokens still shown)."
    )
    priced_call_count: int = Field(description="Number of paid leaf calls that carried usage.")


class PreviewTraceNode(BaseModel):
    """One node of the execution trace, flattened to materialized-path coordinates (no raw payloads)."""

    node_id: str = Field(description="Identifier of the executed node.")
    kind: str = Field(description="The node's kind (resolves its labels/schema in the registry).")
    status: str = Field(description="Outcome: success / failed / skipped.")
    duration_ms: float = Field(description="Wall-clock execution time in milliseconds.")
    depth: int = Field(description="0 for a root stage, +1 per nesting level.")
    node_path: str = Field(description="Materialized path (root = bare id, nested = dotted path).")
    parent_path: str | None = Field(description="The parent node's path (null for a root stage).")
    item_index: int | None = Field(
        description="Enclosing ForEach item index (null outside a fan-out)."
    )
    score: float | None = Field(description="Quality score of a scored node (null otherwise).")
    error_type: str | None = Field(
        description="Exception class name when the node failed (else null)."
    )
    error_message: str | None = Field(
        description="Exception message when the node failed (else null)."
    )


class PreviewResponse(BaseModel):
    """The bounded dry-run report — what an ingestion WOULD produce on one document, nothing persisted."""

    ok: bool = Field(
        description="True when the run delivered a RunBundle; false when a node failed (see error/trace)."
    )
    source_filename: str = Field(description="The previewed source's filename.")
    ir: PreviewIrSummary | None = Field(
        description="The produced IR summary, or null when the run failed before parsing."
    )
    chunk_count: int = Field(
        description="Total chunks the run produced (the preview returns the first N)."
    )
    chunks: list[PreviewChunk] = Field(
        description="The first N chunks, in reading order (text truncated)."
    )
    chunks_truncated: bool = Field(
        description="True when chunk_count exceeds the returned chunk list."
    )
    vector_set_count: int = Field(
        description="Number of chunk vector sets the embed stage produced."
    )
    cost: PreviewCost = Field(description="The run's actual metered spend on this document.")
    trace: list[PreviewTraceNode] = Field(
        description="The full per-node execution trace, roots first."
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal notices (e.g. 0 chunks)."
    )
    failed_node_id: str | None = Field(
        default=None, description="The deepest node that raised, when the run failed (else null)."
    )
    failed_node_kind: str | None = Field(
        default=None, description="The failing node's kind, when the run failed (else null)."
    )
    error: str | None = Field(
        default=None, description="The failure reason when ok is false (else null)."
    )


class PreviewJobAccepted(BaseModel):
    """Acknowledgement of an asynchronous (worker-side) dry-run preview submission."""

    preview_id: str = Field(
        description="The pollable preview id — GET the result endpoint with it until status is terminal."
    )
    status: str = Field(description="The initial job status (always 'pending' right after submit).")


class PreviewJobResult(BaseModel):
    """A poll of an asynchronous dry-run preview — its coarse status plus the report once complete."""

    preview_id: str = Field(description="The preview id being polled.")
    status: str = Field(
        description="Coarse job state: pending (queued) / running / done (result present) / failed "
        "(the worker job itself crashed — distinct from a DATA failure, which is a done result with "
        "ok=false)."
    )
    result: PreviewResponse | None = Field(
        default=None,
        description="The bounded dry-run report, present only when status is 'done' (else null). A "
        "failed NODE is DATA here: status 'done' with result.ok = false.",
    )
    error: str | None = Field(
        default=None,
        description="The reason the worker job itself failed (status 'failed'), else null.",
    )


__all__ = [
    "PreviewIrSummary",
    "PreviewChunk",
    "PreviewCost",
    "PreviewTraceNode",
    "PreviewResponse",
    "PreviewJobAccepted",
    "PreviewJobResult",
]

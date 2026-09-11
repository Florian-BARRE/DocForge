# ====== Code Summary ======
# The preview_pipeline arq task — a NON-PERSISTENT ingestion dry-run that runs in the WORKER (where
# docling + every heavy dep the app image lacks are present), so an interactive preview works for ALL
# pipelines, not only the pure/sidecar ones the app's inline fast-lane can parse. It rehydrates one
# source (uploaded bytes passed through the queue, OR an already-ingested document read back from S3),
# runs the FULL ingest graph through the shared PreviewRunner, prices the actual spend, and RETURNS the
# bounded PreviewResponse as the arq job result (kept in Redis with a short TTL for the client to poll).
# It writes NOTHING durable: no document/chunk row, no S3 blob, no Qdrant point, no execution-tree row —
# the RunTranslator and every ingestion writer are never invoked. A failed node (or a bad/unmigratable
# blob) is DATA (ok=false), never an exception, so a poll always resolves to a PreviewResponse.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT
from shared_libs.pipelines.ingest import BlobNormalizationError, BlobNormalizer, IngestPipeline
from shared_libs.pipelines.ingest.estimate import RateTable
from shared_libs.pipelines.preview import (
    PreviewContractBuilder,
    PreviewGraphError,
    PreviewInputError,
    PreviewProjector,
    PreviewResponse,
    PreviewRunner,
    PreviewSourceResolver,
)
from shared_libs.public_models import SourceDocument

# Module-level stateless runner — the engine keeps all run-scoped state in its own RunContext, so one
# instance is safe to reuse across every preview job (exactly like the app's inline PreviewRunner).
_RUNNER = PreviewRunner()


def _resolve_blob(collection: Any, blob_override: dict | None) -> dict:
    """Pick + auto-heal the blob to dry-run: candidate override → stored pipeline → stock default."""
    chosen = (
        blob_override
        or collection.pipeline
        or IngestPipeline.default_blob().model_dump(mode="json")
    )
    return BlobNormalizer.normalize(chosen)


async def _resolve_source(
    collection_id: uuid.UUID,
    document_id: str | None,
    content: bytes | None,
    declared_meta: dict[str, Any],
    filename: str,
    max_bytes: int,
) -> SourceDocument:
    """
    Build the dry-run SourceDocument — uploaded bytes passed through the queue OR a rehydrated document.

    Args:
        collection_id (uuid.UUID): The owning collection (bounds an existing-document rehydrate).
        document_id (str | None): An already-ingested document to rehydrate (mutually exclusive with
            ``content``).
        content (bytes | None): Uploaded source bytes carried through the queue (already size-capped).
        declared_meta (dict): Caller-declared metadata for the uploaded-bytes case.
        filename (str): The uploaded file's name (ignored for the rehydrate case).
        max_bytes (int): The preview size ceiling for a rehydrated document's bytes.

    Returns:
        SourceDocument: The same run-input shape a real ingestion binds.

    Raises:
        PreviewInputError: Neither/both sources supplied, unknown/foreign document, or missing bytes.
    """
    # 1. Uploaded bytes win — no store read needed (the app carried the capped bytes on the queue).
    if content is not None:
        return SourceDocument(filename=filename, content=content, declared_meta=dict(declared_meta))

    # 2. Otherwise rehydrate an already-ingested document read-only (bytes + declared meta from S3/PG).
    if document_id is None:
        raise PreviewInputError("neither uploaded bytes nor a document id were supplied")
    document = await CONTEXT.database.documents.get(uuid.UUID(document_id))
    if document is None or document.collection_id != collection_id:
        raise PreviewInputError(f"document {document_id} not found in collection {collection_id}")
    return await PreviewSourceResolver(CONTEXT.database).from_document(document, max_bytes)


async def preview_pipeline(
    ctx: dict[str, Any],
    preview_id: str,
    collection_id: str,
    document_id: str | None = None,
    content: bytes | None = None,
    declared_meta: dict[str, Any] | None = None,
    filename: str = "upload",
    blob_override: dict | None = None,
    max_chunks: int | None = None,
) -> dict[str, Any]:
    """
    Run one NON-PERSISTENT ingestion dry-run and RETURN the bounded preview (the arq job result).

    Args:
        ctx (dict): arq's context dict (unused — services live on CONTEXT).
        preview_id (str): The preview/job id (for correlation/logging; arq keys the result by it).
        collection_id (str): The collection whose contract + pipeline the run uses (UUID as string).
        document_id (str | None): An already-ingested document to dry-run (XOR ``content``).
        content (bytes | None): Uploaded source bytes carried on the queue (already size-capped).
        declared_meta (dict | None): Caller-declared metadata for the uploaded-bytes case.
        filename (str): The uploaded file's name (used only with ``content``).
        blob_override (dict | None): A candidate pipeline blob to preview instead of the stored one.
        max_chunks (int | None): How many preview chunks to return (clamped by the worker ceiling).

    Returns:
        dict: The ``PreviewResponse`` as a JSON-mode dict. A failed node / bad blob / bad input is
            DATA (ok=false) in the result, never a raised exception.
    """
    config = CONTEXT.RUNTIME_CONFIG
    cid = uuid.UUID(collection_id)
    declared = declared_meta or {}
    ceiling = config.WORKER_PREVIEW_MAX_CHUNKS
    effective_max_chunks = ceiling if max_chunks is None else max(0, min(max_chunks, ceiling))
    max_bytes = config.WORKER_PREVIEW_MAX_BYTES

    # 1. Load the collection + schema (reads only). An unknown collection is DATA, not a crash.
    collection = await CONTEXT.database.collections.get(cid)
    if collection is None:
        return PreviewProjector.failed_precheck(
            filename, f"collection {collection_id} not found"
        ).model_dump(mode="json")
    schema = await CONTEXT.database.collections.get_schema(cid)

    # 2. Resolve the source + contract + blob. A bad source/blob is a pre-run DATA failure (ok=false).
    try:
        source = await _resolve_source(cid, document_id, content, declared, filename, max_bytes)
        contract = PreviewContractBuilder.build(collection, schema)
        blob = _resolve_blob(collection, blob_override)
    except (PreviewInputError, BlobNormalizationError) as exc:
        CONTEXT.logger.info(f"Preview {preview_id} pre-run failure: {exc}")
        return PreviewProjector.failed_precheck(filename, str(exc)).model_dump(mode="json")

    # 3. Run the FULL ingest graph through the shared pure runner — NO persistence of any kind happens
    #    on this path (no RunTranslator, no ingestion writer, no execution-tree write). A failed node
    #    returns (None, partial record) as DATA; only a bad/unbuildable blob raises (still DATA here).
    source_filename = source.filename
    try:
        bundle, record = await _RUNNER.run(
            blob,
            source,
            contract,
            timeout_seconds=config.WORKER_PREVIEW_RUN_TIMEOUT_SECONDS,
        )
    except PreviewGraphError as exc:
        CONTEXT.logger.info(f"Preview {preview_id} graph failure: {exc}")
        return PreviewProjector.failed_precheck(source_filename, str(exc)).model_dump(mode="json")

    # 4. Price the ACTUAL spend against the collection's rates (same meter as a real run), project the
    #    bounded report, and RETURN it — arq stores it as the job result for the client to poll.
    rates = RateTable.from_overrides(getattr(collection, "estimate_overrides", None))
    response: PreviewResponse = PreviewProjector.project(
        bundle,
        record,
        rates,
        source_filename=source_filename,
        max_chunks=effective_max_chunks,
        text_max_chars=config.WORKER_PREVIEW_CHUNK_TEXT_MAX_CHARS,
    )
    CONTEXT.logger.info(
        f"Preview {preview_id} complete for '{source_filename}' "
        f"(ok={response.ok}, chunks={response.chunk_count})"
    )
    return response.model_dump(mode="json")


__all__ = ["preview_pipeline"]

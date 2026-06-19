# ====== Code Summary ======
# Pages section — a derived view over a document's blocks.
# Endpoints: list / get / screenshot (read) + reingest (triggers full-document re-run).

# ====== Standard Library Imports ======
import asyncio
import uuid
from collections import defaultdict
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException, Response

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.error_handling import auto_handle_errors
from backend.routers.collections.documents.helpers import DocumentOps
from backend.routers.collections.documents.pages.models import (
    BlockInfo,
    PageDetailResponse,
    PageInfo,
    PageListResponse,
    PageReingestResponse,
)
from libs.data.storage.s3.client import S3Client

# Render resolution for on-the-fly page screenshots — 2× zoom matches S1 figure crop quality.
_PAGE_RENDER_ZOOM: float = 2.0

router = APIRouter(tags=["pages"])


@router.get("/list", response_model=PageListResponse)
@auto_handle_errors
async def list_pages(collection_id: uuid.UUID, document_id: uuid.UUID) -> PageListResponse:
    """List the document's pages with per-page block/figure/table/chunk counts."""
    # 1. Load blocks + chunks for the document
    await _require_document(collection_id, document_id)
    blocks, chunks = await _blocks_and_chunks(document_id)

    # 2. Aggregate per page
    chunks_per_page = _chunks_per_page(chunks)
    pages: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"n_blocks": 0, "n_figures": 0, "n_tables": 0, "has_text": False}
    )
    for b in blocks:
        agg = pages[b.page]
        agg["n_blocks"] += 1
        agg["n_figures"] += int(b.type.lower() == "figure")
        agg["n_tables"] += int(b.type.lower() == "table")
        agg["has_text"] = agg["has_text"] or bool(b.text and b.text.strip())

    # 3. Shape ordered page list
    infos = [
        PageInfo(page=p, n_chunks=len(chunks_per_page.get(p, [])), **agg)
        for p, agg in sorted(pages.items())
    ]
    return PageListResponse(document_id=document_id, total_pages=len(infos), pages=infos)


@router.get("/{page_number}", response_model=PageDetailResponse)
@auto_handle_errors
async def get_page(
    collection_id: uuid.UUID, document_id: uuid.UUID, page_number: int
) -> PageDetailResponse:
    """Full info for one page: its blocks, concatenated text, and covering chunk ids."""
    # 1. Load + filter to this page
    await _require_document(collection_id, document_id)
    blocks, chunks = await _blocks_and_chunks(document_id)
    page_blocks = [b for b in blocks if b.page == page_number]

    # 2. Shape blocks + text + covering chunks
    return PageDetailResponse(
        document_id=document_id, page=page_number, n_blocks=len(page_blocks),
        blocks=[_block_info(b) for b in page_blocks],
        text=_page_text(page_blocks),
        chunk_ids=[str(c["id"]) for c in chunks if page_number in _chunk_pages(c)],
    )


@router.get("/{page_number}/screenshot")
@auto_handle_errors
async def get_page_screenshot(
    collection_id: uuid.UUID, document_id: uuid.UUID, page_number: int
) -> Response:
    """Render a page as PNG on-the-fly from the original PDF."""
    # 1. Document must exist + be fully processed
    doc = await _require_document(collection_id, document_id)
    if doc.status != "done":
        raise HTTPException(status_code=409, detail=f"Document {document_id} not done (status={doc.status!r}).")

    # 2. Download original PDF from object store
    pdf_key = S3Client.key_original(doc.source_hash)
    if not await CONTEXT.s3.exists(pdf_key):
        raise HTTPException(status_code=404, detail="Original PDF not available in object store.")
    pdf_bytes = await CONTEXT.s3.download(pdf_key)

    # 3. Render the requested page in a thread pool (PyMuPDF is CPU-bound)
    loop = asyncio.get_event_loop()
    try:
        png_bytes = await loop.run_in_executor(None, _render_page_png, pdf_bytes, page_number)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return Response(content=png_bytes, media_type="image/png")


@router.post("/{page_number}/reingest", response_model=PageReingestResponse)
@auto_handle_errors
async def reingest_page(
    collection_id: uuid.UUID, document_id: uuid.UUID, page_number: int
) -> PageReingestResponse:
    """
    Re-run the pipeline for a page.

    The pipeline operates at document granularity (a page is a derived view), so this re-runs
    the whole document. The Merkle cache keeps unchanged stages cheap.
    """
    doc = await _require_document(collection_id, document_id)
    job_id = await DocumentOps.reingest(doc, force=True)
    return PageReingestResponse(
        document_id=document_id, page=page_number, job_id=job_id,
        note="Pages are a derived view; the whole document was re-enqueued (force re-run).",
    )


# ─── Private helpers ─────────────────────────────────────────────────────────


async def _require_document(collection_id: uuid.UUID, document_id: uuid.UUID):
    """Load a document scoped to its collection, else 404."""
    async with CONTEXT.postgres.session() as session:
        doc = await CONTEXT.document_repo.get_by_id(session, document_id)
    if doc is None or doc.collection_id != collection_id:
        raise HTTPException(
            status_code=404, detail=f"Document {document_id} not found in collection {collection_id}."
        )
    return doc


async def _blocks_and_chunks(document_id: uuid.UUID) -> tuple[list[Any], list[dict]]:
    """Load a document's blocks (reading order) and chunks in one place."""
    async with CONTEXT.postgres.session() as session:
        blocks = await CONTEXT.block_repo.get_by_document(session, document_id)
        chunks = await CONTEXT.chunk_repo.get_by_document(session, document_id)
    return blocks, chunks


def _chunk_pages(chunk: dict) -> list[int]:
    """Read the page list from a chunk's provenance (empty when absent)."""
    prov = chunk.get("prov") if isinstance(chunk.get("prov"), dict) else {}
    return prov.get("pages", []) or []


def _chunks_per_page(chunks: list[dict]) -> dict[int, list[str]]:
    """Index chunk ids by the pages they cover."""
    by_page: dict[int, list[str]] = defaultdict(list)
    for c in chunks:
        for p in _chunk_pages(c):
            by_page[p].append(str(c["id"]))
    return by_page


def _page_text(page_blocks: list[Any]) -> str:
    """Concatenate the text of a page's blocks (already in reading order)."""
    return "\n".join(b.text for b in page_blocks if b.text and b.text.strip())


def _block_info(b: Any) -> BlockInfo:
    """
    Map a BlockModel to a BlockInfo, including type-specific payload + chain lineage.

    chain_traces are persisted INSIDE type_data (no schema migration needed) but the
    response surfaces them as a top-level field so the frontend doesn't have to
    poke into the enrichment payload to find provenance.
    """
    raw_type_data = b.type_data or {}
    chain_traces = list(raw_type_data.get("chain_traces", []) or [])
    # Strip chain_traces from the exposed type_data — keep figure/table fields clean.
    visible_type_data: dict | None = (
        {k: v for k, v in raw_type_data.items() if k != "chain_traces"}
        if raw_type_data
        else None
    )
    return BlockInfo(
        id=b.id,
        type=b.type,
        page=b.page,
        text=b.text,
        bbox=list(b.bbox) if b.bbox else [],
        type_data=visible_type_data,
        chain_traces=chain_traces,
    )


def _render_page_png(pdf_bytes: bytes, page_number: int) -> bytes:
    """
    Render a single PDF page as a PNG using PyMuPDF (synchronous, runs in thread pool).

    Args:
        pdf_bytes (bytes): Raw PDF content.
        page_number (int): 0-indexed page number to render.

    Returns:
        bytes: PNG-encoded page image.

    Raises:
        ValueError: If page_number is out of range for the given PDF.
    """
    import fitz  # PyMuPDF

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        if page_number >= doc.page_count:
            raise ValueError(f"Page {page_number} out of range (document has {doc.page_count} page(s)).")
        matrix = fitz.Matrix(_PAGE_RENDER_ZOOM, _PAGE_RENDER_ZOOM)
        pix = doc[page_number].get_pixmap(matrix=matrix, alpha=False)
        return pix.tobytes("png")

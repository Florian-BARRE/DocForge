# ====== Code Summary ======
# MCP tools for the documents domain — thin wrappers over sdk.documents (the admission path).
# Browsing an admitted document (list/get/pages/ir/chunks/delete) lives in the explorer tools.
# upload_document_bytes is the remote-caller counterpart of upload_document: it never touches the
# MCP server's filesystem or PathGuard, since the bytes travel base64-encoded inside the tool call
# itself — the only way a streamable-HTTP caller without a shared MCP_UPLOAD_DIR volume can upload.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Annotated, Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP
from pydantic import Field

# ====== Local Project Imports ======
from ..path_guard import PathGuard
from ._encoding import DEFAULT_MAX_INLINE_UPLOAD_BYTES, decode_base64_arg


def register(
    mcp: FastMCP,
    sdk: AsyncClient,
    path_guard: PathGuard,
    max_inline_upload_bytes: int = DEFAULT_MAX_INLINE_UPLOAD_BYTES,
) -> None:
    """Register document tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
        path_guard (PathGuard): Resolves/confines `file_path` before it reaches the SDK — a no-op
            on stdio, but on streamable-HTTP it refuses any path outside the configured inbox (or
            everything, if no inbox is configured) so a remote caller can never read an arbitrary
            file off the MCP container's filesystem.
        max_inline_upload_bytes (int): Decoded-size ceiling for `upload_document_bytes`'
            `content_base64` (operator-configured via `MCP_MAX_INLINE_UPLOAD_BYTES`).
    """

    @mcp.tool()
    async def upload_document(
        file_path: str, collection_id: str, metadata: dict[str, Any] | None = None
    ) -> Any:
        """
        Upload a local file into a collection and enqueue its ingestion (async — poll
        get_job(job_id) or get_document(document_id) for status). On stdio, `file_path` must be an
        absolute path readable by the MCP server; on streamable-HTTP it must resolve inside the
        operator-configured upload inbox (MCP_UPLOAD_DIR), or the call is refused. `metadata` is
        validated against the collection's declared schema (unknown field names are rejected).
        """
        resolved = path_guard.resolve(file_path)
        accepted = await sdk.documents.upload(collection_id, resolved, metadata=metadata)
        return accepted.model_dump(mode="json")

    @mcp.tool()
    async def upload_document_bytes(
        collection_id: str,
        filename: str,
        content_base64: str,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """
        Upload a document by sending its raw bytes instead of a server-local file path — use this
        one (never upload_document) when you hold the file's content yourself and are connected
        over streamable-HTTP, since upload_document requires a path already staged inside the
        operator's MCP_UPLOAD_DIR inbox. `content_base64` is the file's exact bytes, standard
        base64-encoded. `filename` (e.g. "report.pdf") drives format/extension detection
        server-side, so include the real extension. Same async contract as upload_document: poll
        wait_for_job(job_id) or get_job(job_id) afterwards. `metadata` is validated against the
        collection's declared schema (unknown field names are rejected).
        """
        content = decode_base64_arg(content_base64, max_bytes=max_inline_upload_bytes)
        accepted = await sdk.documents.upload(
            collection_id, content, metadata=metadata, filename=filename
        )
        return accepted.model_dump(mode="json")

    @mcp.tool()
    async def set_document_enabled(document_id: str, enabled: bool) -> Any:
        """Toggle a document's searchability (reversible, no re-ingest)."""
        result = await sdk.documents.set_enabled(document_id, enabled)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def update_document_metadata(document_id: str, values: dict[str, Any]) -> Any:
        """
        Update a document's metadata VALUES in place - document-scope fields only (chunk-scope or
        unknown fields are rejected 422, as is an empty `values`). `values` maps field name -> new
        value (scalar, or a list for list-typed fields). Filterable changes are instant;
        semantic/lexical changes trigger a background re-embed and return a `job_id` to poll with
        wait_for_job / get_job (`reembedding` / `reembed_fields` tell you which). 404 when the
        document is unknown.
        """
        result = await sdk.documents.update_metadata(document_id, values)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def get_document_markdown(
        document_id: str,
        pages: Annotated[
            str | None,
            Field(
                description="1-based pages to render: '5', '5-7' or '5,7-9'. Omit for the whole "
                "document (can be ~50k chars). 422 when malformed or past the last page."
            ),
        ] = None,
    ) -> Any:
        """
        The document rendered as Markdown, generated on the fly from the canonical IR.

        Prefer `pages` (1-based, e.g. '5' or '5-7'): call get_document_outline first to find the
        pages of a section; the whole document can be ~50k chars. With `pages`, each page is
        preceded by a citable page marker.
        """
        view = await sdk.documents.get_markdown(document_id, pages=pages)
        return view.model_dump(mode="json")

    @mcp.tool()
    async def get_document_html(
        document_id: str,
        pages: Annotated[
            str | None,
            Field(
                description="1-based pages to render: '5', '5-7' or '5,7-9'. Omit for the whole "
                "document (can be ~50k chars). 422 when malformed or past the last page."
            ),
        ] = None,
    ) -> Any:
        """
        The document rendered as HTML, generated on the fly from the canonical IR.

        Prefer `pages` (1-based, e.g. '5' or '5-7'): call get_document_outline first to find the
        pages of a section; the whole document can be ~50k chars. With `pages`, each page is
        preceded by a citable page marker.
        """
        view = await sdk.documents.get_html(document_id, pages=pages)
        return view.model_dump(mode="json")

    @mcp.tool()
    async def reingest_document(document_id: str, force: bool = False) -> Any:
        """Re-run the full ingestion of a single document (force bypasses the doc cache)."""
        accepted = await sdk.documents.reingest(document_id, force)
        return accepted.model_dump(mode="json")

    @mcp.tool()
    async def purge_document_trace_payloads(document_id: str) -> Any:
        """
        Reclaim every stored full execution-trace payload of a single document's jobs — the heavy
        per-node raw input/output bytes the opt-in `trace_verbosity='full'` tier accumulates in the
        object store. Idempotent: a document that stored nothing returns zeros (not an error); 404
        only when the document itself is unknown. Best-effort — always succeeds and reports
        `purged_jobs` (jobs considered) + `deleted_objects` (object-store objects removed).
        """
        result = await sdk.documents.purge_trace_payloads(document_id)
        return result.model_dump(mode="json")

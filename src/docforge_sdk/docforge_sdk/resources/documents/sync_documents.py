# ====== Code Summary ======
# GENERATED FILE — DO NOT EDIT. Derived from async_documents.py by scripts/generate_sync.py;
# regenerate with `uv run --frozen python scripts/generate_sync.py` from src/docforge_sdk
# (tests/unit/test_sync_codegen.py fails when this file drifts from its async source).
# The synchronous document admission and searchability control resource: the blocking shell over
# the shared ``_DocumentsSpecs`` builders.

# ====== Standard Library Imports ======
from pathlib import Path
from typing import Any

# ====== Local Project Imports ======
from ...models.documents import (
    DocumentEnabledResponse,
    DocumentView,
    MetadataUpdateResponse,
    UploadAccepted,
)
from ...models.trace import TracePurgeResult
from .._base import SyncResource
from .specs import _DocumentsSpecs


class SyncDocuments(SyncResource, _DocumentsSpecs):
    """Synchronous document admission and searchability control."""

    def upload(
        self,
        collection_id: str,
        file: str | Path | bytes,
        metadata: dict[str, Any] | None = None,
        filename: str | None = None,
    ) -> UploadAccepted:
        """
        Upload a document for asynchronous ingestion.

        Args:
            collection_id (str): The target collection's UUID.
            file (str | Path | bytes): A local file path or the raw bytes to ingest.
            metadata (dict[str, Any] | None): Declared metadata (field → value).
            filename (str | None): Override name; defaults to the path's name, else ``"upload"``.

        Returns:
            UploadAccepted: The admitted document id, its ingestion job id and the duplicate flag.
        """
        files, data = self._upload_parts(collection_id, file, metadata, filename)
        return self._transport.upload(self._DOCUMENTS_PATH, files, data, UploadAccepted)

    def set_enabled(self, document_id: str, enabled: bool) -> DocumentEnabledResponse:
        """
        Toggle a document's searchability (hides or reveals all its chunks).

        Args:
            document_id (str): The document to toggle.
            enabled (bool): True to make searchable, False to hide from search.

        Returns:
            DocumentEnabledResponse: The document id and its new searchability state.
        """
        return self._transport.request(
            self._set_enabled_spec(document_id, enabled), DocumentEnabledResponse
        )

    def update_metadata(self, document_id: str, values: dict[str, Any]) -> MetadataUpdateResponse:
        """
        Update a document's metadata VALUES in place (document-scope fields only).

        Filterable changes apply instantly; semantic/lexical changes enqueue a background re-embed
        whose ``job_id`` can be polled. Unknown/chunk-scope fields or bad values raise a
        ValidationError (422); an unknown document raises NotFound (404).

        Args:
            document_id (str): The document to edit.
            values (dict[str, Any]): Map of metadata field name -> new value (at least one entry).

        Returns:
            MetadataUpdateResponse: Written fields, whether a re-embed was queued, and its job id.
        """
        return self._transport.request(
            self._update_metadata_spec(document_id, values), MetadataUpdateResponse
        )

    def reingest(
        self, document_id: str, force: bool = False, replay_from: str | None = None
    ) -> UploadAccepted:
        """
        Re-run the full ingestion of a single document.

        Args:
            document_id (str): The document to re-ingest.
            force (bool): Bypass the document cache and re-run every stage.
            replay_from (str | None): Replay only this post-IR stage and its downstream on the
                persisted IR (no re-parse); 422 ``replay_unsupported`` lists the allowed stages.

        Returns:
            UploadAccepted: The fresh ingestion job handle (poll it for status).
        """
        return self._transport.request(
            self._reingest_spec(document_id, force, replay_from), UploadAccepted
        )

    def purge_trace_payloads(self, document_id: str) -> TracePurgeResult:
        """
        Reclaim one document's stored full execution-trace payloads (the heavy per-node raw bytes).

        Idempotent: a document that stored no full-trace payloads returns zeros, not an error (404
        only when the document itself is unknown). Best-effort server-side, so the call always
        succeeds and reports the counts.

        Args:
            document_id (str): The document whose trace payloads are purged.

        Returns:
            TracePurgeResult: Jobs considered + object-store objects deleted.
        """
        return self._transport.request(
            self._purge_trace_payloads_spec(document_id), TracePurgeResult
        )

    def get_markdown(
        self, document_id: str, download: bool = False, pages: str | None = None
    ) -> DocumentView:
        """
        Render a document as an on-the-fly markdown view generated from the canonical IR.

        Args:
            document_id (str): The document to render.
            download (bool): When true, ask the server for the attachment-style response (the caller
                still only gets the text back; the flag only affects the server-side response header).
            pages (str | None): Render only these 1-based pages ('5', '5-7', '5,7-9'); the whole
                document when None (the parameter is then not sent at all).

        Returns:
            DocumentView: The rendered markdown body and its ``text/markdown`` content type.
        """
        content, mime_type = self._transport.get_text_typed(
            self._markdown_path(document_id), params={"download": download, "pages": pages}
        )
        return DocumentView(content=content, mime_type=mime_type)

    def get_html(
        self, document_id: str, download: bool = False, pages: str | None = None
    ) -> DocumentView:
        """
        Render a document as an on-the-fly HTML view generated from the canonical IR.

        Args:
            document_id (str): The document to render.
            download (bool): When true, ask the server for the attachment-style response (the caller
                still only gets the text back; the flag only affects the server-side response header).
            pages (str | None): Render only these 1-based pages ('5', '5-7', '5,7-9'); the whole
                document when None (the parameter is then not sent at all).

        Returns:
            DocumentView: The rendered HTML body and its ``text/html`` content type.
        """
        content, mime_type = self._transport.get_text_typed(
            self._html_path(document_id), params={"download": download, "pages": pages}
        )
        return DocumentView(content=content, mime_type=mime_type)

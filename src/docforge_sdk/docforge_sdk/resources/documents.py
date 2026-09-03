# ====== Code Summary ======
# The documents resource: multipart upload (admission) and the searchability toggle. Upload routes
# through the transport's multipart helper; the toggle is a plain PATCH. All URL/body/multipart logic
# lives once in the pure _DocumentsSpecs mixin so the async/sync shells differ ONLY by ``await``.

# ====== Standard Library Imports ======
import json
from pathlib import Path
from typing import Any

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.documents import DocumentEnabledResponse, DocumentView, EnabledPatch, UploadAccepted
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _DocumentsSpecs(_ResourceMixin):
    """Pure request builders for the documents endpoints — the single source of URL/body/multipart logic."""

    _DOCUMENTS_PATH = "/documents"

    @staticmethod
    def _upload_parts(
        collection_id: str,
        file: str | Path | bytes,
        metadata: dict[str, Any] | None,
        filename: str | None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """
        Build the multipart ``files`` and ``data`` parts of an upload from a path or raw bytes.

        Args:
            collection_id (str): The target collection's UUID.
            file (str | Path | bytes): A local file path or the raw bytes to ingest.
            metadata (dict[str, Any] | None): Declared metadata; serialised to the JSON form field.
            filename (str | None): Override name; defaults to the path's name, else ``"upload"``.

        Returns:
            tuple[dict[str, Any], dict[str, str]]: The httpx ``files`` mapping and the form ``data``.
        """
        # 1. Resolve raw bytes + a filename from either a local path or in-memory bytes.
        if isinstance(file, bytes):
            content, resolved_name = file, (filename or "upload")
        else:
            path = Path(file)
            content, resolved_name = path.read_bytes(), (filename or path.name)

        # 2. Assemble the multipart file part and the accompanying form fields.
        files = {"file": (resolved_name, content)}
        data = {"collection_id": collection_id, "metadata": json.dumps(metadata or {})}
        return files, data

    def _set_enabled_spec(self, document_id: str, enabled: bool) -> RequestSpec:
        """
        Build the spec for toggling a document's searchability.

        Args:
            document_id (str): The document to toggle.
            enabled (bool): The desired searchability state.

        Returns:
            RequestSpec: A PATCH on the document's ``/enabled`` sub-resource.
        """
        return RequestSpec(
            "PATCH",
            f"{self._DOCUMENTS_PATH}/{document_id}/enabled",
            json=EnabledPatch(enabled=enabled).model_dump(mode="json"),
        )

    def _reingest_spec(self, document_id: str, force: bool) -> RequestSpec:
        """A POST re-running the full ingestion of one document (``force`` bypasses the doc cache)."""
        return RequestSpec(
            "POST", f"{self._DOCUMENTS_PATH}/{document_id}/reingest", params={"force": force}
        )

    def _markdown_path(self, document_id: str) -> str:
        """
        Build the API-relative path to a document's on-the-fly markdown view.

        Args:
            document_id (str): The document to render.

        Returns:
            str: The path to the document's ``/markdown`` sub-resource.
        """
        return f"{self._DOCUMENTS_PATH}/{document_id}/markdown"

    def _html_path(self, document_id: str) -> str:
        """
        Build the API-relative path to a document's on-the-fly HTML view.

        Args:
            document_id (str): The document to render.

        Returns:
            str: The path to the document's ``/html`` sub-resource.
        """
        return f"{self._DOCUMENTS_PATH}/{document_id}/html"


class AsyncDocuments(AsyncResource, _DocumentsSpecs):
    """Asynchronous document admission and searchability control."""

    async def upload(
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
        return await self._transport.upload(self._DOCUMENTS_PATH, files, data, UploadAccepted)

    async def set_enabled(self, document_id: str, enabled: bool) -> DocumentEnabledResponse:
        """
        Toggle a document's searchability (hides or reveals all its chunks).

        Args:
            document_id (str): The document to toggle.
            enabled (bool): True to make searchable, False to hide from search.

        Returns:
            DocumentEnabledResponse: The document id and its new searchability state.
        """
        return await self._transport.request(
            self._set_enabled_spec(document_id, enabled), DocumentEnabledResponse
        )

    async def reingest(self, document_id: str, force: bool = False) -> UploadAccepted:
        """
        Re-run the full ingestion of a single document.

        Args:
            document_id (str): The document to re-ingest.
            force (bool): Bypass the document cache and re-run every stage.

        Returns:
            UploadAccepted: The fresh ingestion job handle (poll it for status).
        """
        return await self._transport.request(
            self._reingest_spec(document_id, force), UploadAccepted
        )

    async def get_markdown(self, document_id: str, download: bool = False) -> DocumentView:
        """
        Render a document as an on-the-fly markdown view generated from the canonical IR.

        Args:
            document_id (str): The document to render.
            download (bool): When true, ask the server for the attachment-style response (the caller
                still only gets the text back; the flag only affects the server-side response header).

        Returns:
            DocumentView: The rendered markdown body and its ``text/markdown`` content type.
        """
        content, mime_type = await self._transport.get_text_typed(
            self._markdown_path(document_id), params={"download": download}
        )
        return DocumentView(content=content, mime_type=mime_type)

    async def get_html(self, document_id: str, download: bool = False) -> DocumentView:
        """
        Render a document as an on-the-fly HTML view generated from the canonical IR.

        Args:
            document_id (str): The document to render.
            download (bool): When true, ask the server for the attachment-style response (the caller
                still only gets the text back; the flag only affects the server-side response header).

        Returns:
            DocumentView: The rendered HTML body and its ``text/html`` content type.
        """
        content, mime_type = await self._transport.get_text_typed(
            self._html_path(document_id), params={"download": download}
        )
        return DocumentView(content=content, mime_type=mime_type)


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

    def reingest(self, document_id: str, force: bool = False) -> UploadAccepted:
        """Re-run the full ingestion of a single document (``force`` bypasses the doc cache)."""
        return self._transport.request(self._reingest_spec(document_id, force), UploadAccepted)

    def get_markdown(self, document_id: str, download: bool = False) -> DocumentView:
        """
        Render a document as an on-the-fly markdown view generated from the canonical IR.

        Args:
            document_id (str): The document to render.
            download (bool): When true, ask the server for the attachment-style response (the caller
                still only gets the text back; the flag only affects the server-side response header).

        Returns:
            DocumentView: The rendered markdown body and its ``text/markdown`` content type.
        """
        content, mime_type = self._transport.get_text_typed(
            self._markdown_path(document_id), params={"download": download}
        )
        return DocumentView(content=content, mime_type=mime_type)

    def get_html(self, document_id: str, download: bool = False) -> DocumentView:
        """
        Render a document as an on-the-fly HTML view generated from the canonical IR.

        Args:
            document_id (str): The document to render.
            download (bool): When true, ask the server for the attachment-style response (the caller
                still only gets the text back; the flag only affects the server-side response header).

        Returns:
            DocumentView: The rendered HTML body and its ``text/html`` content type.
        """
        content, mime_type = self._transport.get_text_typed(
            self._html_path(document_id), params={"download": download}
        )
        return DocumentView(content=content, mime_type=mime_type)


__all__ = ["AsyncDocuments", "SyncDocuments"]

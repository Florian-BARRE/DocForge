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
from ..models.documents import DocumentEnabledResponse, EnabledPatch, UploadAccepted
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


__all__ = ["AsyncDocuments", "SyncDocuments"]

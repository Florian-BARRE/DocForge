# ====== Code Summary ======
# Documents sub-API: the admission path (multipart upload -> enqueue) and the searchability
# toggle, under /api/v1/documents.

from __future__ import annotations

# ====== Standard Library Imports ======
import json
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class DocumentsApi(LoggerClass):
    """Document admission (upload) and the searchability toggle."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """
        Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def upload(
        self, file_path: str, collection_id: str, metadata: dict[str, Any] | None = None
    ) -> Any:
        """
        Upload a local file into a collection and enqueue its ingestion (async processing).

        Args:
            file_path (str): Absolute path to the local file to upload.
            collection_id (str): Target collection UUID.
            metadata (dict | None): Declared metadata, validated against the collection schema.

        Returns:
            Any: UploadAccepted — document_id, job_id, duplicate.
        """
        # 1. collection_id and metadata are both form fields alongside the file part
        data = {"collection_id": collection_id, "metadata": json.dumps(metadata or {})}
        return await self._t.upload("/documents", file_path, data=data)

    async def set_enabled(self, document_id: str, enabled: bool) -> Any:
        """
        Toggle a document's searchability (reversible, no re-ingest).

        Args:
            document_id (str): Document UUID.
            enabled (bool): True to make it searchable, False to hide it from search.

        Returns:
            Any: DocumentEnabledResponse — document_id, enabled.
        """
        return await self._t.patch(f"/documents/{document_id}/enabled", {"enabled": enabled})

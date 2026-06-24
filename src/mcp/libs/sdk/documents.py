# ====== Code Summary ======
# Documents sub-API: ingest / list / get / update / reingest / delete under
# /api/v1/collections/{collection_id}/documents.

from __future__ import annotations

# ====== Standard Library Imports ======
import json
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class DocumentsApi(LoggerClass):
    """Document lifecycle endpoints (a sub-resource of a collection)."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def ingest(
        self, collection_id: str, file_path: str, metadata: dict[str, Any] | None = None
    ) -> Any:
        """
        Upload a local file and enqueue the pipeline (async processing).

        Args:
            collection_id (str): Target collection UUID.
            file_path (str): Absolute path to the local file to ingest.
            metadata (dict | None): Optional user metadata, validated against the schema.

        Returns:
            Any: Ingest acknowledgement (doc_id, status, duplicate, job_id).
        """
        # 1. Serialise optional metadata as the JSON form field the endpoint expects
        data = {"metadata": json.dumps(metadata)} if metadata else None

        # 2. Upload
        return await self._t.upload(
            f"/collections/{collection_id}/documents/ingest", file_path, data=data
        )

    async def list(
        self,
        collection_id: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Any:
        """
        List documents in a collection with optional filter, pagination, and sort.

        Args:
            collection_id (str): Target collection UUID.
            status (str | None): Filter by status (pending/running/done/error).
            limit (int): Page size (1–500).
            offset (int): Page offset.
            sort_by (str): created_at | filename | status | file_size.
            sort_order (str): asc | desc.

        Returns:
            Any: Paginated documents with the total match count.
        """
        return await self._t.get(
            f"/collections/{collection_id}/documents/list",
            params={
                "status": status,
                "limit": limit,
                "offset": offset,
                "sort_by": sort_by,
                "sort_order": sort_order,
            },
        )

    async def get(self, collection_id: str, document_id: str) -> Any:
        """
        Full document record with aggregated pipeline state (counts, file availability, errors).

        Args:
            collection_id (str): Target collection UUID.
            document_id (str): Document UUID.

        Returns:
            Any: The enriched document record.
        """
        return await self._t.get(f"/collections/{collection_id}/documents/{document_id}")

    async def update(
        self, collection_id: str, document_id: str, metadata: dict[str, Any], reindex: bool = False
    ) -> Any:
        """
        Merge a metadata patch into a document's user metadata (a null value removes a key).

        Args:
            collection_id (str): Target collection UUID.
            document_id (str): Document UUID.
            metadata (dict): Partial metadata patch.
            reindex (bool): Also sync the changed fields into the live index.

        Returns:
            Any: The update result (changed fields, reindex outcome).
        """
        return await self._t.post(
            f"/collections/{collection_id}/documents/{document_id}/update",
            {"metadata": metadata, "reindex": reindex},
        )

    async def reingest(self, collection_id: str, document_id: str, force: bool = False) -> Any:
        """
        Re-enqueue the full pipeline for a document.

        Args:
            collection_id (str): Target collection UUID.
            document_id (str): Document UUID.
            force (bool): Bypass the Merkle node cache and rebuild every stage from scratch.

        Returns:
            Any: Reingest acknowledgement (job_id, status).
        """
        return await self._t.post(
            f"/collections/{collection_id}/documents/{document_id}/reingest",
            {"force": force},
        )

    async def delete(self, collection_id: str, document_id: str) -> Any:
        """
        Delete a document and all associated data (cascade across Postgres / Qdrant / S3).

        Args:
            collection_id (str): Target collection UUID.
            document_id (str): Document UUID.

        Returns:
            Any: Deletion result (qdrant points + blob disposition).
        """
        return await self._t.delete(
            f"/collections/{collection_id}/documents/{document_id}/delete"
        )

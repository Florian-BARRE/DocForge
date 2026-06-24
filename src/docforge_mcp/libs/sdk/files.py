# ====== Code Summary ======
# Files sub-API: presigned URLs for a document's artefacts (original / markdown / pdf / figure)
# under /api/v1/collections/{collection_id}/documents/{document_id}.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class FilesApi(LoggerClass):
    """Presigned-URL endpoints for document file artefacts."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def original(self, collection_id: str, document_id: str) -> Any:
        """Presigned URL for the original uploaded file."""
        return await self._t.get(self._base(collection_id, document_id) + "/original")

    async def markdown(self, collection_id: str, document_id: str) -> Any:
        """Presigned URL for the faithful Markdown view produced by S1."""
        return await self._t.get(self._base(collection_id, document_id) + "/markdown")

    async def pdf(self, collection_id: str, document_id: str) -> Any:
        """Presigned URL for the canonical PDF artefact."""
        return await self._t.get(self._base(collection_id, document_id) + "/pdf")

    async def figure(self, collection_id: str, document_id: str, block_id: str) -> Any:
        """
        Presigned URL for a figure crop PNG (keyed by block id).

        Args:
            collection_id (str): Target collection UUID.
            document_id (str): Document UUID.
            block_id (str): Block id of the figure (may itself contain slashes — sent as a path).

        Returns:
            Any: A presigned URL response.
        """
        return await self._t.get(self._base(collection_id, document_id) + f"/figures/{block_id}")

    @staticmethod
    def _base(collection_id: str, document_id: str) -> str:
        """Build the document-scoped path root shared by every files endpoint."""
        return f"/collections/{collection_id}/documents/{document_id}"

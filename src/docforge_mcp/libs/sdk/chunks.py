# ====== Code Summary ======
# Chunks sub-API: list / get / update under
# /api/v1/collections/{collection_id}/documents/{document_id}/chunks.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class ChunksApi(LoggerClass):
    """Chunk endpoints (the atomic retrieval unit and source of truth for raw_text)."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def list(
        self, collection_id: str, document_id: str, limit: int = 50, offset: int = 0
    ) -> Any:
        """
        List a document's chunks in reading order, paginated.

        Args:
            collection_id (str): Target collection UUID.
            document_id (str): Document UUID.
            limit (int): Page size (1–500).
            offset (int): Page offset.

        Returns:
            Any: Paginated chunks with the total count.
        """
        return await self._t.get(
            self._base(collection_id, document_id) + "/list",
            params={"limit": limit, "offset": offset},
        )

    async def get(self, collection_id: str, document_id: str, chunk_id: str) -> Any:
        """
        Full materialisation of a chunk (raw_text, embed_text, provenance).

        Args:
            collection_id (str): Target collection UUID.
            document_id (str): Document UUID.
            chunk_id (str): Chunk UUID.

        Returns:
            Any: The chunk record.
        """
        return await self._t.get(self._base(collection_id, document_id) + f"/{chunk_id}")

    async def update(
        self,
        collection_id: str,
        document_id: str,
        chunk_id: str,
        raw_text: str | None = None,
        embed_text: str | None = None,
        reindex: bool = False,
    ) -> Any:
        """
        Manually correct a chunk's text, optionally re-embedding its content vectors.

        At least one of ``raw_text`` / ``embed_text`` must be provided.

        Args:
            collection_id (str): Target collection UUID.
            document_id (str): Document UUID.
            chunk_id (str): Chunk UUID.
            raw_text (str | None): Corrected raw text.
            embed_text (str | None): Corrected embed text (re-embedded when reindex=True).
            reindex (bool): Re-embed the content vectors from the new embed_text.

        Returns:
            Any: The update result.
        """
        return await self._t.post(
            self._base(collection_id, document_id) + f"/{chunk_id}/update",
            {"raw_text": raw_text, "embed_text": embed_text, "reindex": reindex},
        )

    @staticmethod
    def _base(collection_id: str, document_id: str) -> str:
        """Build the chunks path root for a document."""
        return f"/collections/{collection_id}/documents/{document_id}/chunks"

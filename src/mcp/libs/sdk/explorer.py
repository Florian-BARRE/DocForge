# ====== Code Summary ======
# Explorer sub-API: the read-only browse surface over a collection's documents — catalogue,
# facts, pages, full IR, chunks — plus the searchability toggles and the coherent delete.
# Mirrors the backend's explorer router (mixed /collections/{id}/documents and /documents/{id}/...
# paths, exactly as the server exposes them).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class ExplorerApi(LoggerClass):
    """The document explorer: catalogue, facts, pages, IR, chunks, toggles and delete."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """
        Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def list_documents(self, collection_id: str) -> Any:
        """
        Return a collection's documents, newest first — the browse catalogue.

        Args:
            collection_id (str): The collection's UUID.
        """
        return await self._t.get(f"/collections/{collection_id}/documents")

    async def get_document(self, document_id: str) -> Any:
        """Return one document's full facts and resolved document-level metadata."""
        return await self._t.get(f"/documents/{document_id}")

    async def get_pages(self, document_id: str) -> Any:
        """Return a document's pages, in order — geometry, routing, render blob reference."""
        return await self._t.get(f"/documents/{document_id}/pages")

    async def get_ir(self, document_id: str) -> Any:
        """Return the document's full canonical IR (blocks, tables, figures, enrichments)."""
        return await self._t.get(f"/documents/{document_id}/ir")

    async def get_chunks(self, document_id: str) -> Any:
        """Return a document's chunks — enriched text, composition and generated metadata."""
        return await self._t.get(f"/documents/{document_id}/chunks")

    async def delete_document(self, document_id: str) -> Any:
        """Delete a document everywhere (Qdrant points, PG cascade, orphan-only blob purge)."""
        return await self._t.delete(f"/documents/{document_id}")

    async def set_chunk_enabled(self, chunk_id: str, enabled: bool) -> Any:
        """
        Toggle one chunk's searchability (reversible, no re-embed).

        Args:
            chunk_id (str): The chunk's UUID.
            enabled (bool): True to make it searchable, False to hide it.
        """
        return await self._t.patch(f"/chunks/{chunk_id}/enabled", {"enabled": enabled})

    async def set_chunks_enabled(self, chunk_ids: list[str], enabled: bool) -> Any:
        """
        Toggle several chunks' searchability to the same state in one call.

        Args:
            chunk_ids (list[str]): The chunks to toggle (at least one).
            enabled (bool): The state to apply to every listed chunk.
        """
        return await self._t.patch(
            "/chunks/enabled", {"chunk_ids": chunk_ids, "enabled": enabled}
        )

# ====== Code Summary ======
# Pages sub-API: list / get / screenshot (PNG bytes) / reingest under
# /api/v1/collections/{collection_id}/documents/{document_id}/pages.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class PagesApi(LoggerClass):
    """Page endpoints (a derived view over a document's blocks)."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def list(self, collection_id: str, document_id: str) -> Any:
        """List the document's pages with per-page block/figure/table/chunk counts."""
        return await self._t.get(self._base(collection_id, document_id) + "/list")

    async def get(self, collection_id: str, document_id: str, page_number: int) -> Any:
        """
        Full info for one page: its blocks, concatenated text, and covering chunk ids.

        Args:
            collection_id (str): Target collection UUID.
            document_id (str): Document UUID.
            page_number (int): 0-indexed page number.

        Returns:
            Any: The page detail record.
        """
        return await self._t.get(self._base(collection_id, document_id) + f"/{page_number}")

    async def screenshot(self, collection_id: str, document_id: str, page_number: int) -> bytes:
        """
        Render a page as a PNG on-the-fly from the original PDF.

        Args:
            collection_id (str): Target collection UUID.
            document_id (str): Document UUID.
            page_number (int): 0-indexed page number.

        Returns:
            bytes: PNG-encoded page image.
        """
        return await self._t.get_bytes(
            self._base(collection_id, document_id) + f"/{page_number}/screenshot"
        )

    async def reingest(self, collection_id: str, document_id: str, page_number: int) -> Any:
        """
        Re-run the pipeline for a page (re-runs the whole document — pages are a derived view).

        Args:
            collection_id (str): Target collection UUID.
            document_id (str): Document UUID.
            page_number (int): 0-indexed page number.

        Returns:
            Any: Reingest acknowledgement.
        """
        return await self._t.post(
            self._base(collection_id, document_id) + f"/{page_number}/reingest"
        )

    @staticmethod
    def _base(collection_id: str, document_id: str) -> str:
        """Build the pages path root for a document."""
        return f"/collections/{collection_id}/documents/{document_id}/pages"

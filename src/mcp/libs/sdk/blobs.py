# ====== Code Summary ======
# Blobs sub-API: the content-addressed blob byte stream under /api/v1/blobs/{content_hash}
# (page renders, figure crops, the canonical PDF, the original upload).

from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class BlobsApi(LoggerClass):
    """The content-addressed blob byte stream."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """
        Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def get(self, content_hash: str) -> tuple[bytes, str]:
        """
        Fetch a blob's raw bytes and its registered mime type.

        Args:
            content_hash (str): The blob's content address (sha256 hex).

        Returns:
            tuple[bytes, str]: (raw bytes, mime type).
        """
        return await self._t.get_bytes(f"/blobs/{content_hash}")

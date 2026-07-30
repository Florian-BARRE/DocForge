# ====== Code Summary ======
# The blobs resource — fetch a content-addressed blob's raw bytes with its registered mime type. The
# endpoint streams bytes (not JSON), so both shells route through the transport's get_bytes_typed
# helper and wrap its (bytes, mime) pair into a BlobContent. Path logic lives once in _BlobsSpecs.

# ====== Local Project Imports ======
from ..models.blobs import BlobContent
from ._base import AsyncResource, SyncResource, _ResourceMixin


class _BlobsSpecs(_ResourceMixin):
    """Pure path builder for the blobs endpoint — the single source of URL logic."""

    _BLOBS_PATH = "/blobs"

    def _blob_path(self, content_hash: str) -> str:
        """
        Build the API-relative path for a content-addressed blob.

        Args:
            content_hash (str): The blob's content hash (its key).

        Returns:
            str: The path to the blob resource.
        """
        return f"{self._BLOBS_PATH}/{content_hash}"


class AsyncBlobs(AsyncResource, _BlobsSpecs):
    """Asynchronous content-addressed blob fetch."""

    async def get(self, content_hash: str) -> BlobContent:
        """
        Fetch a blob's raw bytes and its server-registered media type.

        Args:
            content_hash (str): The blob's content hash (its key).

        Returns:
            BlobContent: The raw bytes paired with the registered mime type.
        """
        content, mime_type = await self._transport.get_bytes_typed(self._blob_path(content_hash))
        return BlobContent(content=content, mime_type=mime_type)


class SyncBlobs(SyncResource, _BlobsSpecs):
    """Synchronous content-addressed blob fetch."""

    def get(self, content_hash: str) -> BlobContent:
        """
        Fetch a blob's raw bytes and its server-registered media type.

        Args:
            content_hash (str): The blob's content hash (its key).

        Returns:
            BlobContent: The raw bytes paired with the registered mime type.
        """
        content, mime_type = self._transport.get_bytes_typed(self._blob_path(content_hash))
        return BlobContent(content=content, mime_type=mime_type)


__all__ = ["AsyncBlobs", "SyncBlobs"]

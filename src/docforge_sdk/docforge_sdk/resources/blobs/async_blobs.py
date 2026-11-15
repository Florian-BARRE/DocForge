# ====== Code Summary ======
# The asynchronous content-addressed blob fetch resource: the awaiting shell over the shared
# ``_BlobsSpecs`` builders.

# ====== Local Project Imports ======
from ...models.blobs import BlobContent
from .._base import AsyncResource
from .specs import _BlobsSpecs


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

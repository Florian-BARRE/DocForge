# ====== Code Summary ======
# GENERATED FILE — DO NOT EDIT. Derived from async_blobs.py by scripts/generate_sync.py;
# regenerate with `uv run --frozen python scripts/generate_sync.py` from src/docforge_sdk
# (tests/unit/test_sync_codegen.py fails when this file drifts from its async source).
# The synchronous content-addressed blob fetch resource: the blocking shell over the shared
# ``_BlobsSpecs`` builders.

# ====== Local Project Imports ======
from ...models.blobs import BlobContent
from .._base import SyncResource
from .specs import _BlobsSpecs


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

# ====== Code Summary ======
# TransferBundleStore — the S3 side of collection export/import bundles, behind
# CollectionTransferFacade: upload a local file (publish a finished export archive, or stage an
# uploaded import bundle), download a bundle to a local file, delete one, and stream one in bounded
# windows. It touches no Postgres: the façade owns the tracking rows. Internal collaborator of
# CollectionTransferFacade; import the façade, not this class, from outside.

# ====== Standard Library Imports ======
from collections.abc import AsyncIterator
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.services.db.s3 import S3Client, S3ObjectApi


class TransferBundleStore:
    """Move `.dcexport` bundle bytes between local files / HTTP streams and S3."""

    def __init__(self, s3: S3Client) -> None:
        self._s3 = s3

    async def stream(self, s3_key: str, chunk_size: int) -> AsyncIterator[bytes]:
        """
        Stream a bundle's bytes from S3 in bounded chunks (never whole in memory).

        The shared S3 client is kept open for the whole iteration (exiting the ``client()`` scope
        does not close it), so the caller can pull windows straight from S3 to the HTTP response.
        """
        async with self._s3.client() as client:
            async for chunk in S3ObjectApi.stream(client, self._s3.bucket, s3_key, chunk_size):
                yield chunk

    async def put_file(self, s3_key: str, path: Any, content_type: str) -> int:
        """
        Upload a local file to S3 under ``s3_key`` with a known Content-Length (no buffering).

        Atomic: the key becomes valid only once the PUT lands. Used both to publish a finished
        export archive and to stage an uploaded import bundle.

        Args:
            s3_key (str): The object key to publish under.
            path (Any): The local file path to upload.
            content_type (str): The object's content type.

        Returns:
            int: The uploaded object's size in bytes.
        """
        async with self._s3.client() as client:
            return await S3ObjectApi.put_file(client, self._s3.bucket, s3_key, path, content_type)

    async def download_to(self, s3_key: str, path: Any) -> None:
        """Download a bundle object from S3 to a local file (streamed to disk, never whole in memory)."""
        async with self._s3.client() as client:
            await S3ObjectApi.download_to(client, self._s3.bucket, s3_key, path)

    async def delete(self, s3_key: str) -> None:
        """Delete one bundle object from S3 (idempotent; a failure propagates to the caller)."""
        async with self._s3.client() as client:
            await S3ObjectApi.delete(client, self._s3.bucket, s3_key)


__all__ = ["TransferBundleStore"]

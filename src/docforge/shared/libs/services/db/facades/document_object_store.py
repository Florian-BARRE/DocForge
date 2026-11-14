# ====== Code Summary ======
# DocumentObjectStore — the S3 byte reads behind DocumentsFacade: a document's ORIGINAL uploaded
# bytes (the object key is the source hash) and a bounded-window stream of any registered blob. It
# touches no Postgres: the façade resolves rows, this collaborator only moves bytes. Internal
# collaborator of DocumentsFacade; import the façade, not this class, from outside.

# ====== Standard Library Imports ======
from collections.abc import AsyncIterator

# ====== Internal Project Imports ======
from shared_libs.services.db.s3 import S3Client, S3ObjectApi


class DocumentObjectStore:
    """Read a document's source bytes and stream blob bytes from the object store."""

    def __init__(self, s3: S3Client) -> None:
        self._s3 = s3

    async def read_source(self, source_hash: str) -> bytes:
        """
        Read a document's ORIGINAL uploaded bytes from S3 (the object key is the source hash).

        Backs the worker's full ingest run, which starts from the original file; a replay never
        calls it (it stands on the persisted IR, so a garbage-collected source must not fail it).

        Args:
            source_hash (str): The document's ``source_hash`` — its content address and S3 key.

        Returns:
            bytes: The original file's bytes.
        """
        async with self._s3.client() as s3:
            return await S3ObjectApi.get(s3, self._s3.bucket, source_hash)

    async def stream(self, s3_key: str, chunk_size: int) -> AsyncIterator[bytes]:
        """Yield an object's bytes from S3 in bounded windows (client scope held for the iteration)."""
        async with self._s3.client() as s3:
            async for chunk in S3ObjectApi.stream(s3, self._s3.bucket, s3_key, chunk_size):
                yield chunk


__all__ = ["DocumentObjectStore"]

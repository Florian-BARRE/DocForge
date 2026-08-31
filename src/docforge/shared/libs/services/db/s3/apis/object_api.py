# ====== Code Summary ======
# S3ObjectApi — the object operations of the blob store: put many, get, and delete, all keyed by
# (bucket, key). Content-addressing lives one layer up (the key IS the blob's content hash, computed
# by the façade); this api is purely key-based. It runs against the client the S3Client hands out,
# the way the Postgres apis run against a session.

# ====== Standard Library Imports ======
import os
from collections.abc import AsyncIterator, Sequence
from typing import Any

# ====== Local Project Imports ======
from ..objects import S3Object


class S3ObjectApi:
    """Static object operations (put / get / delete) for the blob store."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("S3ObjectApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def put_many(client: Any, bucket: str, objects: Sequence[S3Object]) -> None:
        """Store several objects (a document's original / PDF / crops) in one client scope."""
        for obj in objects:
            await client.put_object(
                Bucket=bucket, Key=obj.key, Body=obj.data, ContentType=obj.content_type
            )

    @staticmethod
    async def get(client: Any, bucket: str, key: str) -> bytes:
        """Read an object's bytes by key."""
        response = await client.get_object(Bucket=bucket, Key=key)
        async with response["Body"] as stream:
            return await stream.read()

    @staticmethod
    async def put_file(client: Any, bucket: str, key: str, path: Any, content_type: str) -> int:
        """
        Upload a file's bytes at ``path`` under ``key`` WITHOUT loading it into memory.

        Used to publish a large collection-export bundle: the open file handle is streamed as the
        request body (a plain PUT sends it with a known Content-Length). Returns the byte size.

        Args:
            client (Any): The S3 client from S3Client.client().
            bucket (str): The target bucket.
            key (str): The object key.
            path (Any): The local file path to upload.
            content_type (str): The object's content type.

        Returns:
            int: The uploaded object's size in bytes.
        """
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            await client.put_object(
                Bucket=bucket,
                Key=key,
                Body=handle,
                ContentType=content_type,
                ContentLength=size,
            )
        return size

    @staticmethod
    async def download_to(client: Any, bucket: str, key: str, path: Any) -> None:
        """
        Stream an object's bytes to a local file at ``path`` in bounded chunks (never whole in memory).

        The read side of ``put_file`` — used to fetch a collection-export bundle before extraction.
        """
        response = await client.get_object(Bucket=bucket, Key=key)
        # Use the StreamingBody's async chunk iterator rather than a sized ``read(n)``: under
        # ``async with`` the body can unwrap to a raw aiohttp ClientResponse whose ``read()`` rejects
        # a size argument. ``iter_chunks`` is the portable path (see S3ObjectApi.stream).
        with open(path, "wb") as handle:
            async for chunk in response["Body"].iter_chunks(1024 * 1024):
                if chunk:
                    handle.write(chunk)

    @staticmethod
    async def stream(
        client: Any, bucket: str, key: str, chunk_size: int = 1024 * 1024
    ) -> AsyncIterator[bytes]:
        """
        Yield an object's bytes in bounded chunks, never the whole object in memory.

        The delivery read side of ``put_file``: used to stream a collection-export bundle straight to
        an HTTP client behind auth (a ``StreamingResponse``) without buffering a multi-GB file. The
        caller must keep the ``client`` scope open for the lifetime of the iteration.

        Args:
            client (Any): The S3 client from S3Client.client().
            bucket (str): The source bucket.
            key (str): The object key.
            chunk_size (int): The per-read window in bytes.

        Yields:
            bytes: The next window of the object's bytes.
        """
        response = await client.get_object(Bucket=bucket, Key=key)
        # aiobotocore's StreamingBody exposes an async chunk iterator; use it rather than a sized
        # ``read(n)`` — under ``async with`` the body can unwrap to a raw aiohttp ClientResponse
        # whose ``read()`` rejects a size argument, so ``iter_chunks`` is the portable path.
        async for chunk in response["Body"].iter_chunks(chunk_size):
            if chunk:
                yield chunk

    @staticmethod
    async def delete(client: Any, bucket: str, key: str) -> None:
        """Delete an object by key (no error if it is already absent)."""
        await client.delete_object(Bucket=bucket, Key=key)

    @staticmethod
    async def delete_many(client: Any, bucket: str, keys: Sequence[str]) -> None:
        """Delete several objects — the blob purge path (call with reference-checked keys only).

        One batched ``delete_objects`` per 1000 keys (the S3 limit) instead of a request per key —
        a document/collection purge of N orphan blobs is ⌈N/1000⌉ round-trips, not N.
        """
        keys = list(keys)
        for start in range(0, len(keys), 1000):
            batch = keys[start : start + 1000]
            await client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
            )


__all__ = ["S3ObjectApi"]

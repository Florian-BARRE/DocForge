# ====== Code Summary ======
# S3ObjectApi — the object operations of the blob store: put many, get, and delete, all keyed by
# (bucket, key). Content-addressing lives one layer up (the key IS the blob's content hash, computed
# by the façade); this api is purely key-based. It runs against the client the S3Client hands out,
# the way the Postgres apis run against a session.

# ====== Standard Library Imports ======
from collections.abc import Sequence
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

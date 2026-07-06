# ====== Code Summary ======
# S3ObjectApi — the object operations of the blob store: put one or many, get, delete, and exists,
# all keyed by (bucket, key). Content-addressing lives one layer up (the key IS the blob's content
# hash, computed by the façade); this api is purely key-based. It runs against the client the
# S3Client hands out, the way the Postgres apis run against a session.

# ====== Standard Library Imports ======
from collections.abc import Sequence
from typing import Any

# ====== Third-Party Library Imports ======
from botocore.exceptions import ClientError

# ====== Local Project Imports ======
from ..objects import S3Object

# Error codes a missing object surfaces as (SeaweedFS / S3 vary on head vs get).
_NOT_FOUND_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


class S3ObjectApi:
    """Static object operations (put / get / delete / exists) for the blob store."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("S3ObjectApi is a static-only class and cannot be instantiated.")

    @staticmethod
    async def put(
        client: Any,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        """Store one object under ``key`` — overwrites (content-addressed, so it is the same bytes)."""
        await client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)

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
        """Delete several objects — the blob purge path (call with reference-checked keys only)."""
        for key in keys:
            await client.delete_object(Bucket=bucket, Key=key)

    @staticmethod
    async def exists(client: Any, bucket: str, key: str) -> bool:
        """Return whether an object exists under ``key``."""
        try:
            await client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _NOT_FOUND_CODES:
                return False
            raise


__all__ = ["S3ObjectApi"]

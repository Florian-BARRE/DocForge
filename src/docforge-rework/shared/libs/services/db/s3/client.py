# ====== Code Summary ======
# S3Client — the connection gateway to the object store (SeaweedFS / any S3-compatible), the blob
# analogue of PostgresClient and QdrantClient. It holds the aioboto3 session + endpoint config and
# hands out a client via the `client()` async context manager (like PostgresClient.session()); the
# S3 apis run their operations against it. Credentials are infra (from RUNTIME_CONFIG), never
# hardcoded. The Database façade opens ONE client around a document's blobs, not one per blob.

# ====== Standard Library Imports ======
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

# ====== Third-Party Library Imports ======
import aioboto3
from loggerplusplus import LoggerClass


class S3Client(LoggerClass):
    """Connection gateway to the S3-compatible object store — yields a client the apis operate on."""

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
    ) -> None:
        """
        Args:
            endpoint_url (str): S3 endpoint (e.g. ``http://seaweedfs:8333``).
            access_key (str): Access key id.
            secret_key (str): Secret access key.
            bucket (str): The bucket the apis read/write.
            region (str): Region name (SeaweedFS ignores it; kept for the S3 protocol).
        """
        LoggerClass.__init__(self)
        self._session = aioboto3.Session()
        self._endpoint_url = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self.bucket = bucket
        self.logger.info(f"S3Client configured for {endpoint_url} (bucket '{bucket}')")

    @asynccontextmanager
    async def client(self) -> AsyncIterator[Any]:
        """
        Yield an S3 client the apis run against — the object-store analogue of a Postgres session.

        Yields:
            Any: The aioboto3 S3 client (untyped by aioboto3).
        """
        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
        ) as s3:
            yield s3

    async def ensure_bucket(self) -> None:
        """
        Create the configured bucket if it does not exist yet (idempotent, safe to call at boot).

        A fresh object-store volume (a new prod deployment) has no bucket, so the first upload
        would 404/AccessDenied. Calling this at startup makes a clean deploy self-provisioning.
        Existing bucket → head succeeds → no-op; missing bucket → created.

        Raises:
            ClientError: For any S3 error other than a not-found on the head probe.
        """
        # 1. Probe the bucket — a 404/NoSuchBucket means it must be created, anything else re-raises.
        async with self.client() as s3:
            try:
                await s3.head_bucket(Bucket=self.bucket)
                return
            except s3.exceptions.ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code not in ("404", "NoSuchBucket", "NotFound"):
                    raise

            # 2. Absent — create it (tolerate a concurrent creator owning it already).
            try:
                await s3.create_bucket(Bucket=self.bucket)
                self.logger.info(f"Created object-store bucket '{self.bucket}'")
            except s3.exceptions.BucketAlreadyOwnedByYou:
                pass


__all__ = ["S3Client"]

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


__all__ = ["S3Client"]

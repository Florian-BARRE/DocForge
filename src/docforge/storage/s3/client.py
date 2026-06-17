# ====== Code Summary ======
# S3-compatible object store client backed by SeaweedFS.
# Uses aioboto3 (async boto3) targeting SeaweedFS's S3 API (default port 8333).
# All keys are content-addressed (sha256 for originals, blake3 for derived artifacts).
# SeaweedFS is S3-compatible: no code change vs standard S3, only the endpoint URL differs.

# ====== Standard Library Imports ======
from __future__ import annotations

import io
from typing import AsyncIterator

# ====== Third-Party Library Imports ======
import aioboto3
from botocore.exceptions import ClientError
from loggerplusplus import LoggerClass


# Object-store key conventions (content-addressed layout):
#   originals/{sha256}                              — original file bytes
#   derived/{sha256}/pdf                            — original→PDF conversion
#   derived/{sha256}/pages/{n}.png                  — page render PNG (0-indexed)
#   derived/{sha256}/figures/{block_id}.png         — figure crop PNG
#   derived/{sha256}/{s0_fp}/s0_meta.json           — S0 stage output metadata (P2 node cache)
#   derived/{sha256}/{s1_fp}/ir.json                — serialized DocumentIR JSON (pre-enrichment)
#   derived/{sha256}/{s1_fp}/s1_meta.json           — S1 stage output metadata (P2 node cache)
#   derived/{sha256}/{s1_fp}/doc.md                 — faithful markdown view
#   derived/{sha256}/{s2_fp}/ir_enriched.json       — enriched DocumentIR JSON (P3)
#   derived/{sha256}/{s2_fp}/s2_meta.json           — S2 stage output metadata (P3 node cache)


class S3Client(LoggerClass):
    """
    Async S3-compatible client for the DocForge object store (SeaweedFS backend).

    Lifecycle:
        1. ``connect()`` — validates the bucket exists / creates it; call once at startup.
        2. ``upload()``, ``download()``, ``exists()``, ``delete()`` — per-object operations.
        3. ``close()`` — closes the aioboto3 session.

    Key layout:
        All keys follow the content-addressed scheme defined in spec §8.
        Callers should use the static ``key_*`` helpers to construct keys consistently.
    """

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
        public_url: str | None = None,
    ) -> None:
        """
        Initialize the S3 client configuration.

        Args:
            endpoint_url (str): SeaweedFS S3 API URL (internal), e.g. ``http://seaweedfs:8333``.
            access_key (str): S3 access key (from SeaweedFS s3.json config).
            secret_key (str): S3 secret key.
            bucket (str): Target bucket name (created at startup if absent).
            region (str): Region name (SeaweedFS ignores this but boto3 requires it).
            public_url (str | None): External-facing S3 URL used in presigned URLs.
                When set, the internal hostname in presigned URLs is replaced with this
                value so external clients can fetch objects directly. If None, the
                internal endpoint_url is used as-is.
        """
        LoggerClass.__init__(self)
        self._endpoint_url = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._region = region
        self._public_url = public_url
        self._aioboto3_session: aioboto3.Session | None = None

    async def connect(self) -> None:
        """
        Initialize the aioboto3 session and ensure the target bucket exists.

        Raises:
            RuntimeError: If already connected.
            ClientError: If bucket creation fails for any reason other than already-exists.
        """
        # 1. Guard against double-initialization
        if self._aioboto3_session is not None:
            raise RuntimeError(f"S3Client is already connected.")

        # 2. Create the aioboto3 session (not a network call yet)
        self._aioboto3_session = aioboto3.Session()
        self.logger.info(
            f"S3Client initialized → endpoint={self._endpoint_url} bucket={self._bucket}"
        )

        # 3. Ensure the bucket exists (idempotent)
        await self._ensure_bucket()

    async def _ensure_bucket(self) -> None:
        """Create the target bucket if it does not already exist."""
        async with self._s3() as s3:
            try:
                await s3.head_bucket(Bucket=self._bucket)
                self.logger.debug(f"Bucket {self._bucket!r} already exists.")
            except ClientError as exc:
                error_code = exc.response["Error"]["Code"]
                if error_code in ("404", "NoSuchBucket"):
                    # Bucket absent → create it
                    await s3.create_bucket(Bucket=self._bucket)
                    self.logger.info(f"Created bucket {self._bucket!r}.")
                else:
                    raise

    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        """
        Upload bytes to the object store under the given key.

        The operation is idempotent — uploading the same key twice overwrites the object.

        Args:
            key (str): Object key (use the ``key_*`` static helpers to build it).
            data (bytes): Raw bytes to upload.
            content_type (str): MIME type stored as S3 metadata.
        """
        async with self._s3() as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        self.logger.debug(f"Uploaded {len(data)} bytes → s3://{self._bucket}/{key}")

    async def upload_stream(
        self,
        key: str,
        stream: io.IOBase,
        content_type: str = "application/octet-stream",
    ) -> None:
        """
        Upload from a file-like object (avoids loading the entire file into memory).

        Args:
            key (str): Object key.
            stream (io.IOBase): Readable file-like object.
            content_type (str): MIME type.
        """
        async with self._s3() as s3:
            await s3.upload_fileobj(
                stream,
                self._bucket,
                key,
                ExtraArgs={"ContentType": content_type},
            )
        self.logger.debug(f"Streamed upload → s3://{self._bucket}/{key}")

    async def download(self, key: str) -> bytes:
        """
        Download an object and return its bytes.

        Args:
            key (str): Object key.

        Returns:
            bytes: Raw object bytes.

        Raises:
            KeyError: If the key does not exist.
        """
        async with self._s3() as s3:
            try:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
                body = await response["Body"].read()
                return body
            except ClientError as exc:
                if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
                    raise KeyError(f"Object not found: s3://{self._bucket}/{key}") from exc
                raise

    async def exists(self, key: str) -> bool:
        """
        Check whether an object exists without downloading it.

        Args:
            key (str): Object key.

        Returns:
            bool: True if the object exists.
        """
        async with self._s3() as s3:
            try:
                await s3.head_object(Bucket=self._bucket, Key=key)
                return True
            except ClientError as exc:
                if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
                    return False
                raise

    async def delete(self, key: str) -> None:
        """
        Delete a single object (idempotent — deleting a missing key is a no-op).

        Args:
            key (str): Object key.
        """
        async with self._s3() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)
        self.logger.debug(f"Deleted s3://{self._bucket}/{key}")

    async def delete_prefix(self, prefix: str) -> int:
        """
        Delete every object under a key prefix (e.g. all derived artefacts of a source_hash).

        Args:
            prefix (str): Key prefix to purge.

        Returns:
            int: Number of objects deleted.
        """
        deleted = 0
        async with self._s3() as s3:
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                objects = [{"Key": o["Key"]} for o in page.get("Contents", [])]
                if objects:
                    await s3.delete_objects(Bucket=self._bucket, Delete={"Objects": objects})
                    deleted += len(objects)
        self.logger.debug(f"Deleted {deleted} object(s) under s3://{self._bucket}/{prefix}")
        return deleted

    async def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Generate a pre-signed GET URL for the object (serves screenshots, PDFs, etc.).

        Args:
            key (str): Object key.
            expires_in (int): URL validity in seconds (default 1 hour).

        Returns:
            str: Pre-signed URL.
        """
        async with self._s3() as s3:
            url: str = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        # Replace internal hostname with public URL when configured,
        # so callers outside the container network can fetch the object.
        if self._public_url:
            url = url.replace(self._endpoint_url, self._public_url, 1)
        return url

    async def close(self) -> None:
        """Release the aioboto3 session."""
        self._aioboto3_session = None
        self.logger.info(f"S3Client disconnected.")

    # ─── Context manager for aioboto3 client ──────────────────────────────────

    def _s3(self) -> AsyncIterator:
        """
        Return an async context manager that yields a configured S3 client.

        SeaweedFS requires ``addressing_style="path"`` because virtual-hosted-style
        (subdomain-based) addressing is not supported.
        """
        if self._aioboto3_session is None:
            raise RuntimeError(f"S3Client is not connected.")

        return self._aioboto3_session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
            config=self._boto_path_style_config(),
        )

    # ─── Static key builders (content-addressed layout) ───────────────────────

    @staticmethod
    def key_original(source_hash: str) -> str:
        """Key for the original uploaded file."""
        return f"originals/{source_hash}"

    @staticmethod
    def key_pdf(source_hash: str) -> str:
        """Key for the original→PDF conversion artefact."""
        return f"derived/{source_hash}/pdf"

    @staticmethod
    def key_figure_crop(source_hash: str, block_id: str) -> str:
        """Key for a figure crop PNG.

        Docling block IDs use '#/pictures/N' format. The '#' character causes
        presigned-URL signature mismatches with SeaweedFS (boto3 encodes it as '%23'
        in the URL but the SigV2 canonical path differs). We strip '#' and replace
        '/' with '_' so the resulting S3 key only contains URL-safe characters.
        """
        safe_id = block_id.replace("#", "").replace("/", "_").strip("_")
        return f"derived/{source_hash}/figures/{safe_id}.png"

    @staticmethod
    def key_ir(source_hash: str, parse_fp: str) -> str:
        """Key for the serialized DocumentIR JSON."""
        return f"derived/{source_hash}/{parse_fp}/ir.json"

    @staticmethod
    def key_markdown(source_hash: str, serialize_fp: str) -> str:
        """Key for the faithful markdown view."""
        return f"derived/{source_hash}/{serialize_fp}/doc.md"

    @staticmethod
    def key_s0_meta(source_hash: str, s0_fp: str) -> str:
        """Key for the S0 stage output meta JSON (P2 node cache reference)."""
        return f"derived/{source_hash}/{s0_fp}/s0_meta.json"

    @staticmethod
    def key_s1_meta(source_hash: str, s1_fp: str) -> str:
        """Key for the S1 stage output meta JSON (P2 node cache reference)."""
        return f"derived/{source_hash}/{s1_fp}/s1_meta.json"

    @staticmethod
    def key_ir_enriched(source_hash: str, s2_fp: str) -> str:
        """Key for the enriched DocumentIR JSON (P3 — after S2 OCR/VLM enrichment)."""
        return f"derived/{source_hash}/{s2_fp}/ir_enriched.json"

    @staticmethod
    def key_s2_meta(source_hash: str, s2_fp: str) -> str:
        """Key for the S2 stage output meta JSON (P3 node cache reference)."""
        return f"derived/{source_hash}/{s2_fp}/s2_meta.json"

    # ─── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _boto_path_style_config():
        """
        Return a botocore Config enforcing path-style addressing.

        SeaweedFS does not support virtual-hosted-style (e.g. bucket.host:8333).
        Path-style (host:8333/bucket/key) is required.
        """
        from botocore.config import Config

        return Config(s3={"addressing_style": "path"})

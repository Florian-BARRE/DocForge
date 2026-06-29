# ====== Code Summary ======
# ProviderCallCache — cross-document cache for expensive provider calls (OCR, VLM, embed).
# Each cache entry is keyed by a blake3 fingerprint of provider identity + input content.
# Result JSON is stored in SeaweedFS; the DB row holds only the S3 key (result_ref).
# Cache hits avoid redundant API calls for identical inputs across different documents.
#
# Injected into a node as the 'provider_cache' service. It manages its own Postgres
# sessions internally — callers never thread an AsyncSession through the call sites.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy import select

# ====== Internal Project Imports ======
from common_libs.storage.postgres.client import PostgresClient
from common_libs.storage.postgres.models import ProviderCallModel
from common_libs.storage.s3.client import S3Client

# ====== Local Project Imports ======
from .fingerprint import compute_call_fingerprint


class ProviderCallCache(LoggerClass):
    """
    Cross-document cache for provider calls (OCR, VLM, embedding, etc.).

    Backed by the provider_call Postgres table (S3 key pointer) and SeaweedFS
    (full JSON result blob).  The class manages its own DB sessions so callers
    do not need to thread an AsyncSession through every call site.

    Cache key: blake3 of (capability, provider_id, provider_version, params, content_hash).
    S3 key:    provider_cache/{fp[:2]}/{fp}.json  (content-addressed, ~hex-partitioned)
    """

    def __init__(self, postgres: PostgresClient, s3: S3Client) -> None:
        """
        Initialize the ProviderCallCache.

        Args:
            postgres (PostgresClient): Connected Postgres client used to open sessions.
            s3 (S3Client): Connected S3 client used to store/retrieve result JSON blobs.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._s3 = s3

    @staticmethod
    def compute_key(
        capability: str,
        provider_id: str,
        provider_version: str,
        params: dict[str, Any],
        content_hash: str,
    ) -> str:
        """
        Compute the cache key (blake3 fingerprint) for a provider call.

        Args:
            capability (str): Provider capability (e.g. ``"ocr"``, ``"embed"``).
            provider_id (str): Provider identifier (e.g. ``"mistral_ocr_api"``).
            provider_version (str): Provider version string.
            params (dict): Call parameters.
            content_hash (str): Blake3 hash of the content to process.

        Returns:
            str: 64-character hex blake3 digest.
        """
        return compute_call_fingerprint(
            capability=capability,
            provider_id=provider_id,
            provider_version=provider_version,
            params=params,
            content_hash=content_hash,
        )

    async def get(self, call_fp: str) -> str | None:
        """
        Return the cached result JSON string for a completed provider call.

        Opens its own DB session.  On hit: fetches the S3 key from the DB row,
        downloads the JSON blob from SeaweedFS, and returns it as a string.

        Args:
            call_fp (str): Provider call fingerprint (from ``compute_key``).

        Returns:
            str | None: JSON string of the cached result, or None on miss.
        """
        # 1. Query the provider_call table for the S3 key
        async with self._postgres.session() as session:
            result = await session.execute(
                select(ProviderCallModel).where(ProviderCallModel.call_fp == call_fp)
            )
            row = result.scalar_one_or_none()

        if row is None or not row.result_ref:
            self.logger.debug(f"ProviderCallCache MISS: fp={call_fp[:8]}...")
            return None

        # 2. Download the JSON blob from SeaweedFS
        try:
            data = await self._s3.download(row.result_ref)
            self.logger.debug(f"ProviderCallCache HIT: fp={call_fp[:8]}... ref={row.result_ref}")
            return data.decode("utf-8")
        except KeyError:
            # S3 object missing (e.g. bucket wiped) — treat as a cache miss
            self.logger.warning(
                f"ProviderCallCache: S3 object missing for fp={call_fp[:8]}... "
                f"ref={row.result_ref} — treating as miss"
            )
            return None

    async def put(
        self,
        call_fp: str,
        capability: str,
        provider_id: str,
        provider_version: str,
        content_hash: str,
        result_json: str,
    ) -> None:
        """
        Store a provider call result in the cache.

        Uploads the result JSON to SeaweedFS, then upserts the S3 key into the
        provider_call table.  Idempotent: re-running with the same fingerprint
        overwrites the previous entry.

        Args:
            call_fp (str): Provider call fingerprint.
            capability (str): Provider capability (``"ocr"``, ``"vlm"``, etc.).
            provider_id (str): Provider identifier.
            provider_version (str): Provider version.
            content_hash (str): Content hash of the processed input.
            result_json (str): JSON-serialised result object.
        """
        # 1. Upload result JSON to SeaweedFS (hex-partitioned path, ~256 prefix dirs)
        s3_key = f"provider_cache/{call_fp[:2]}/{call_fp}.json"
        await self._s3.upload(s3_key, result_json.encode("utf-8"), content_type="application/json")

        # 2. Upsert the S3 key into the provider_call table
        async with self._postgres.session() as session:
            existing = await session.execute(
                select(ProviderCallModel).where(ProviderCallModel.call_fp == call_fp)
            )
            row = existing.scalar_one_or_none()

            if row is not None:
                row.result_ref = s3_key
            else:
                session.add(
                    ProviderCallModel(
                        call_fp=call_fp,
                        capability=capability,
                        provider_id=provider_id,
                        provider_version=provider_version,
                        content_hash=content_hash,
                        result_ref=s3_key,
                    )
                )
            await session.commit()

        self.logger.debug(f"ProviderCallCache PUT: fp={call_fp[:8]}... ref={s3_key}")

# ====== Code Summary ======
# CacheIOHelpers — static helpers for node-cache read/write against the Postgres-backed
# NodeCache.  S3 (de)serialization of stage artefacts lives in CacheCodec (cache_codec.py);
# the restore/encode/populate methods are re-exposed here as thin delegators so the
# historical CacheIOHelpers.<method> public API stays intact.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.storage.postgres.client import PostgresClient
from common_libs.storage.s3.client import S3Client
from common_libs.pipeline.caches.node_cache import NodeCache
from common_libs.pipeline.ingest.stages.ingest.result import IngestResult
from common_libs.pipeline.ingest.stages.parsing.result import ParseResult
from common_libs.pipeline.ingest.stages.enrich.result import EnrichResult

# ====== Local Project Imports ======
from .cache_codec import CacheCodec
from .cache_encoder import CacheEncoder


class CacheIOHelpers:
    """
    Static helpers for node-cache I/O, with S3 codec re-exposed via delegation.

    Covers directly:
    - ``check`` / ``store`` — consult or write the Postgres-backed node cache

    Delegated to CacheCodec (kept as classmethods for API compatibility):
    - ``restore_s0`` / ``restore_s1`` / ``restore_s2`` — reconstruct stage results from S3
    - ``populate_pdf_bytes`` — lazy-load PDF bytes for a cached S0 result
    - ``encode_s0_meta`` / ``encode_s1_meta`` / ``encode_s2_meta`` — JSON serialization
    """

    logger = loggerplusplus.bind(identifier="CacheIOHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        raise TypeError("CacheIOHelpers is a static-only class and cannot be instantiated.")

    # ─── Node cache read / write ──────────────────────────────────────────────

    @classmethod
    async def check(
        cls,
        postgres: PostgresClient,
        node_cache: NodeCache,
        doc_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
    ) -> str | None:
        """
        Return the cached output_ref from the Postgres-backed node cache.

        Args:
            postgres (PostgresClient): Postgres session factory.
            node_cache (NodeCache): DB-backed node cache.
            doc_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier (e.g. ``"s0"``, ``"s1"``, ``"s2"``).
            fingerprint (str): blake3 Merkle fingerprint for this node.

        Returns:
            str | None: S3 output_ref on cache hit, or None on miss.
        """
        async with postgres.session() as session:
            return await node_cache.get(session, doc_id, node_id, fingerprint)

    @classmethod
    async def store(
        cls,
        postgres: PostgresClient,
        node_cache: NodeCache,
        doc_id: uuid.UUID,
        node_id: str,
        fingerprint: str,
        output_ref: str,
    ) -> None:
        """
        Write the output_ref to the Postgres-backed node cache.

        Args:
            postgres (PostgresClient): Postgres session factory.
            node_cache (NodeCache): DB-backed node cache.
            doc_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier (e.g. ``"s0"``, ``"s1"``, ``"s2"``).
            fingerprint (str): blake3 Merkle fingerprint for this node.
            output_ref (str): S3 key of the node's output artefact to persist.
        """
        async with postgres.session() as session:
            await node_cache.put(session, doc_id, node_id, fingerprint, output_ref)

    # ─── S3 codec delegators (implementation in CacheCodec) ───────────────────

    @classmethod
    async def restore_s0(cls, s3: S3Client, s0_meta_key: str) -> IngestResult:
        """Restore an IngestResult from its S3 meta JSON (delegates to CacheCodec)."""
        return await CacheCodec.restore_s0(s3, s0_meta_key)

    @classmethod
    async def populate_pdf_bytes(cls, s3: S3Client, ingest_result: IngestResult) -> IngestResult:
        """Lazy-load PDF bytes into a cache-restored IngestResult (delegates to CacheCodec)."""
        return await CacheCodec.populate_pdf_bytes(s3, ingest_result)

    @classmethod
    async def restore_s1(cls, s3: S3Client, s1_meta_key: str) -> tuple[ParseResult, DocumentIR]:
        """Restore an ParseResult + DocumentIR from S3 (delegates to CacheCodec)."""
        return await CacheCodec.restore_s1(s3, s1_meta_key)

    @classmethod
    async def restore_s2(cls, s3: S3Client, s2_meta_key: str) -> tuple[EnrichResult, DocumentIR]:
        """Restore an EnrichResult + enriched DocumentIR from S3 (delegates to CacheCodec)."""
        return await CacheCodec.restore_s2(s3, s2_meta_key)

    @staticmethod
    def encode_s0_meta(s0: IngestResult) -> bytes:
        """Serialize an IngestResult to compact JSON bytes (delegates to CacheEncoder)."""
        return CacheEncoder.encode_s0_meta(s0)

    @staticmethod
    def encode_s1_meta(s1: ParseResult, ir_key: str) -> bytes:
        """Serialize ParseResult references to compact JSON bytes (delegates to CacheEncoder)."""
        return CacheEncoder.encode_s1_meta(s1, ir_key)

    @staticmethod
    def encode_s2_meta(s2: EnrichResult, ir_enriched_key: str) -> bytes:
        """Serialize EnrichResult stats to compact JSON bytes (delegates to CacheEncoder)."""
        return CacheEncoder.encode_s2_meta(s2, ir_enriched_key)


# ------------------- Public API ------------------- #
__all__ = ["CacheIOHelpers"]

# ====== Code Summary ======
# CacheIOHelpers — static helpers for node-cache read/write (dry_run in-memory cache vs the
# live Postgres-backed NodeCache).  S3 (de)serialization of stage artefacts lives in
# CacheCodec (cache_codec.py); the restore/encode/populate methods are re-exposed here as
# thin delegators so the historical CacheIOHelpers.<method> public API stays intact.

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
from common_libs.pipeline.stages.s0_ingest.core import S0Result
from common_libs.pipeline.stages.s1_parse.core import S1Result
from common_libs.pipeline.stages.s2_enrich import S2Result

# ====== Local Project Imports ======
from .cache_codec import CacheCodec
from .cache_encoder import CacheEncoder


class CacheIOHelpers:
    """
    Static helpers for node-cache I/O, with S3 codec re-exposed via delegation.

    Covers directly:
    - ``check`` / ``store`` — consult or write the node cache (dry_run vs live)

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
        local_cache: dict[tuple[str, str, str], str],
        dry_run: bool,
    ) -> str | None:
        """
        Return the cached output_ref, consulting local or DB cache based on mode.

        Args:
            postgres (PostgresClient): Postgres session factory (unused in dry_run).
            node_cache (NodeCache): DB-backed node cache (unused in dry_run).
            doc_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier (e.g. ``"s0"``, ``"s1"``, ``"s2"``).
            fingerprint (str): blake3 Merkle fingerprint for this node.
            local_cache (dict): In-memory cache used during dry_run.
            dry_run (bool): When True, consult the in-memory cache instead of Postgres.

        Returns:
            str | None: S3 output_ref on cache hit, or None on miss.
        """
        key = (str(doc_id), node_id, fingerprint)
        if dry_run:
            return local_cache.get(key)
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
        local_cache: dict[tuple[str, str, str], str],
        dry_run: bool,
    ) -> None:
        """
        Write the output_ref to the local cache (dry_run) or DB cache (live).

        Args:
            postgres (PostgresClient): Postgres session factory (unused in dry_run).
            node_cache (NodeCache): DB-backed node cache (unused in dry_run).
            doc_id (uuid.UUID): Document primary key.
            node_id (str): Stage identifier (e.g. ``"s0"``, ``"s1"``, ``"s2"``).
            fingerprint (str): blake3 Merkle fingerprint for this node.
            output_ref (str): S3 key of the node's output artefact to persist.
            local_cache (dict): In-memory cache mutated in place during dry_run.
            dry_run (bool): When True, write to the in-memory cache instead of Postgres.
        """
        key = (str(doc_id), node_id, fingerprint)
        if dry_run:
            local_cache[key] = output_ref
        else:
            async with postgres.session() as session:
                await node_cache.put(session, doc_id, node_id, fingerprint, output_ref)

    # ─── S3 codec delegators (implementation in CacheCodec) ───────────────────

    @classmethod
    async def restore_s0(cls, s3: S3Client, s0_meta_key: str) -> S0Result:
        """Restore an S0Result from its S3 meta JSON (delegates to CacheCodec)."""
        return await CacheCodec.restore_s0(s3, s0_meta_key)

    @classmethod
    async def populate_pdf_bytes(cls, s3: S3Client, s0_result: S0Result) -> S0Result:
        """Lazy-load PDF bytes into a cache-restored S0Result (delegates to CacheCodec)."""
        return await CacheCodec.populate_pdf_bytes(s3, s0_result)

    @classmethod
    async def restore_s1(cls, s3: S3Client, s1_meta_key: str) -> tuple[S1Result, DocumentIR]:
        """Restore an S1Result + DocumentIR from S3 (delegates to CacheCodec)."""
        return await CacheCodec.restore_s1(s3, s1_meta_key)

    @classmethod
    async def restore_s2(cls, s3: S3Client, s2_meta_key: str) -> tuple[S2Result, DocumentIR]:
        """Restore an S2Result + enriched DocumentIR from S3 (delegates to CacheCodec)."""
        return await CacheCodec.restore_s2(s3, s2_meta_key)

    @staticmethod
    def encode_s0_meta(s0: S0Result) -> bytes:
        """Serialize an S0Result to compact JSON bytes (delegates to CacheEncoder)."""
        return CacheEncoder.encode_s0_meta(s0)

    @staticmethod
    def encode_s1_meta(s1: S1Result, ir_key: str) -> bytes:
        """Serialize S1Result references to compact JSON bytes (delegates to CacheEncoder)."""
        return CacheEncoder.encode_s1_meta(s1, ir_key)

    @staticmethod
    def encode_s2_meta(s2: S2Result, ir_enriched_key: str) -> bytes:
        """Serialize S2Result stats to compact JSON bytes (delegates to CacheEncoder)."""
        return CacheEncoder.encode_s2_meta(s2, ir_enriched_key)


# ------------------- Public API ------------------- #
__all__ = ["CacheIOHelpers"]

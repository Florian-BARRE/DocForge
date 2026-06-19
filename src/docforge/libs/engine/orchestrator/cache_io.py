# ====== Code Summary ======
# CacheIOHelpers — static helpers for node-cache read/write and S3 stage-result restore.
# Handles both the dry_run in-memory cache and the live Postgres-backed NodeCache.
# Also owns serialization (encode) and deserialization (restore) of S0/S1/S2 artefacts.

# ====== Standard Library Imports ======
from __future__ import annotations

import json
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from libs.core.ir.models import DocumentIR
from libs.data.storage.postgres.client import PostgresClient
from libs.data.storage.s3.client import S3Client
from libs.engine.node_cache import NodeCache
from libs.engine.stages.s0_ingest import S0Result
from libs.engine.stages.s1_parse import S1Result
from libs.engine.stages.s2_enrich import S2Result


class CacheIOHelpers:
    """
    Static helpers for node-cache I/O and S3 stage-result restore/encode.

    Covers:
    - ``check`` / ``store`` — consult or write the node cache (dry_run vs live)
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

    # ─── S3 restore helpers ───────────────────────────────────────────────────

    @classmethod
    async def restore_s0(cls, s3: S3Client, s0_meta_key: str) -> S0Result:
        """
        Restore an S0Result from its S3 meta JSON.

        ``pdf_bytes`` is set to None (lazy) and populated only if S1 is a miss.

        Args:
            s3 (S3Client): SeaweedFS object store client.
            s0_meta_key (str): S3 key of the S0 meta JSON artefact.

        Returns:
            S0Result: Restored S0 result with ``pdf_bytes=None`` (populated lazily on S1 miss).
        """
        raw = await s3.download(s0_meta_key)
        meta: dict[str, Any] = json.loads(raw)
        return S0Result(
            doc_id=meta["doc_id"],
            source_hash=meta["source_hash"],
            original_key=meta["original_key"],
            pdf_bytes=None,           # Lazy — downloaded only when S1 is a miss
            pdf_key=meta["pdf_key"],
            page_count=meta["page_count"],
            original_filename=meta["original_filename"],
            original_format=meta["original_format"],
            file_size=meta["file_size"],
            needs_ocr=meta["needs_ocr"],
            implicit_meta=meta["implicit_meta"],
        )

    @classmethod
    async def populate_pdf_bytes(cls, s3: S3Client, s0_result: S0Result) -> S0Result:
        """
        Download PDF bytes from S3 into an S0Result that was restored from cache.

        Args:
            s3 (S3Client): SeaweedFS object store client.
            s0_result (S0Result): Cache-restored S0 result with ``pdf_bytes=None``.

        Returns:
            S0Result: A new S0Result identical to the input with ``pdf_bytes`` populated.
        """
        pdf_bytes = await s3.download(s0_result.pdf_key)
        return S0Result(
            doc_id=s0_result.doc_id,
            source_hash=s0_result.source_hash,
            original_key=s0_result.original_key,
            pdf_bytes=pdf_bytes,
            pdf_key=s0_result.pdf_key,
            page_count=s0_result.page_count,
            original_filename=s0_result.original_filename,
            original_format=s0_result.original_format,
            file_size=s0_result.file_size,
            needs_ocr=s0_result.needs_ocr,
            implicit_meta=s0_result.implicit_meta,
        )

    @classmethod
    async def restore_s1(cls, s3: S3Client, s1_meta_key: str) -> tuple[S1Result, DocumentIR]:
        """
        Restore an S1Result and DocumentIR from their S3 meta and IR JSON files.

        Args:
            s3 (S3Client): SeaweedFS object store client.
            s1_meta_key (str): S3 key of the S1 meta JSON artefact.

        Returns:
            tuple[S1Result, DocumentIR]: Restored S1 result and its associated DocumentIR.
        """
        # 1. Download and parse the S1 meta JSON
        raw = await s3.download(s1_meta_key)
        meta: dict[str, Any] = json.loads(raw)

        # 2. Download and reconstruct the DocumentIR from JSON
        ir_raw = await s3.download(meta["ir_key"])
        ir = DocumentIR.model_validate_json(ir_raw)

        # 3. Rebuild the S1Result
        s1_result = S1Result(
            ir=ir,
            markdown_key=meta["markdown_key"],
            figure_crop_keys=meta["figure_crop_keys"],
        )
        return s1_result, ir

    @classmethod
    async def restore_s2(cls, s3: S3Client, s2_meta_key: str) -> tuple[S2Result, DocumentIR]:
        """
        Restore an S2Result and enriched DocumentIR from their S3 meta and IR JSON files.

        Args:
            s3 (S3Client): SeaweedFS object store client.
            s2_meta_key (str): S3 key of the S2 meta JSON artefact.

        Returns:
            tuple[S2Result, DocumentIR]: Restored S2 result and its enriched DocumentIR.
        """
        # 1. Download and parse the S2 meta JSON
        raw = await s3.download(s2_meta_key)
        meta: dict[str, Any] = json.loads(raw)

        # 2. Download and reconstruct the enriched DocumentIR
        ir_raw = await s3.download(meta["ir_enriched_key"])
        enriched_ir = DocumentIR.model_validate_json(ir_raw)

        # 3. Rebuild the S2Result from the cached stats
        s2_result = S2Result(
            ir=enriched_ir,
            budget_spent=meta["budget_spent"],
            figures_processed=meta["figures_processed"],
            ocr_calls=meta["ocr_calls"],
            vlm_calls=meta["vlm_calls"],
            chart_extractions=meta["chart_extractions"],
        )
        return s2_result, enriched_ir

    # ─── Serialization helpers ────────────────────────────────────────────────

    @staticmethod
    def encode_s0_meta(s0: S0Result) -> bytes:
        """
        Serialize S0Result to a compact JSON blob for S3 storage.

        Args:
            s0 (S0Result): S0 stage output to serialize.

        Returns:
            bytes: UTF-8 encoded compact JSON suitable for S3 upload.
        """
        return json.dumps(
            {
                "doc_id": s0.doc_id,
                "source_hash": s0.source_hash,
                "original_key": s0.original_key,
                "pdf_key": s0.pdf_key,
                "page_count": s0.page_count,
                "original_filename": s0.original_filename,
                "original_format": s0.original_format,
                "file_size": s0.file_size,
                "needs_ocr": s0.needs_ocr,
                "implicit_meta": s0.implicit_meta,
            },
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def encode_s1_meta(s1: S1Result, ir_key: str) -> bytes:
        """
        Serialize S1Result references to a compact JSON blob for S3 storage.

        Args:
            s1 (S1Result): S1 stage output containing S3 key references.
            ir_key (str): S3 key where the DocumentIR JSON was uploaded.

        Returns:
            bytes: UTF-8 encoded compact JSON suitable for S3 upload.
        """
        return json.dumps(
            {
                "ir_key": ir_key,
                "markdown_key": s1.markdown_key,
                "figure_crop_keys": s1.figure_crop_keys,
            },
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def encode_s2_meta(s2: S2Result, ir_enriched_key: str) -> bytes:
        """
        Serialize S2Result stats and enriched IR key to a compact JSON blob for S3 storage.

        Args:
            s2 (S2Result): S2 stage output containing enrichment statistics.
            ir_enriched_key (str): S3 key where the enriched DocumentIR JSON was uploaded.

        Returns:
            bytes: UTF-8 encoded compact JSON suitable for S3 upload.
        """
        return json.dumps(
            {
                "ir_enriched_key": ir_enriched_key,
                "budget_spent": s2.budget_spent,
                "figures_processed": s2.figures_processed,
                "ocr_calls": s2.ocr_calls,
                "vlm_calls": s2.vlm_calls,
                "chart_extractions": s2.chart_extractions,
            },
            separators=(",", ":"),
        ).encode("utf-8")

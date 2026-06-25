# ====== Code Summary ======
# CacheCodec — static (de)serialization of S0/S1/S2 stage artefacts to and from S3.
# Owns restore_s0/s1/s2 (reconstruct stage results from S3 JSON), populate_pdf_bytes
# (lazy-load PDF bytes for a cached S0 result), and encode_s0/s1/s2_meta (compact JSON).
# Extracted from CacheIOHelpers so node-cache read/write and S3 codec are separate concerns.

# ====== Standard Library Imports ======
from __future__ import annotations

import json
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.storage.s3.client import S3Client
from common_libs.pipeline.stages.s0_ingest.core import S0Result
from common_libs.pipeline.stages.s1_parse.core import S1Result
from common_libs.pipeline.stages.s2_enrich import S2Result


class CacheCodec:
    """
    Static helpers for S3 (de)serialization of S0/S1/S2 stage artefacts.

    Covers:
    - ``restore_s0`` / ``restore_s1`` / ``restore_s2`` — reconstruct stage results from S3
    - ``populate_pdf_bytes`` — lazy-load PDF bytes for a cached S0 result
    - ``encode_s0_meta`` / ``encode_s1_meta`` / ``encode_s2_meta`` — JSON serialization
    """

    logger = loggerplusplus.bind(identifier="CacheCodec")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        raise TypeError("CacheCodec is a static-only class and cannot be instantiated.")

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
            figures_processed=meta["figures_processed"],
            ocr_calls=meta["ocr_calls"],
            vlm_calls=meta["vlm_calls"],
            chart_extractions=meta["chart_extractions"],
        )
        return s2_result, enriched_ir


# ------------------- Public API ------------------- #
__all__ = ["CacheCodec"]

# ====== Code Summary ======
# CacheEncoder — static serialization of S0/S1/S2 stage results into compact JSON blobs
# for S3 storage.  The matching deserialization (restore_*) lives in CacheCodec
# (cache_codec.py); they are split so encode and decode stay focused single-responsibility
# helpers.

# ====== Standard Library Imports ======
from __future__ import annotations

import json

# ====== Internal Project Imports ======
from common_libs.pipeline.ingest.stages.ingest.result import IngestResult
from common_libs.pipeline.stages.s1_parse.core import S1Result
from common_libs.pipeline.stages.s2_enrich import S2Result


class CacheEncoder:
    """
    Static serialization helpers for S0/S1/S2 stage results.

    Each ``encode_*`` produces a compact UTF-8 JSON blob suitable for S3 upload.  Only the
    fields required to reconstruct the result on a later cache hit are persisted.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        raise TypeError("CacheEncoder is a static-only class and cannot be instantiated.")

    @staticmethod
    def encode_s0_meta(s0: IngestResult) -> bytes:
        """
        Serialize IngestResult to a compact JSON blob for S3 storage.

        Args:
            s0 (IngestResult): S0 stage output to serialize.

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
                "figures_processed": s2.figures_processed,
                "ocr_calls": s2.ocr_calls,
                "vlm_calls": s2.vlm_calls,
                "chart_extractions": s2.chart_extractions,
            },
            separators=(",", ":"),
        ).encode("utf-8")


# ------------------- Public API ------------------- #
__all__ = ["CacheEncoder"]

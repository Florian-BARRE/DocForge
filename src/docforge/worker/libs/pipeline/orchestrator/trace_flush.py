# ====== Code Summary ======
# TraceFlusher — static helper that assembles the implicit_meta dict for a document
# record update and flushes S6 embed-chain traces back onto the document.
# Extracted from StageEngine._build_implicit_meta to keep each concern in its own module.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import DocumentIR
from common_libs.pipeline.stages.s0_ingest.core import S0Result
from common_libs.pipeline.stages.s1_parse.core import S1Result
from common_libs.pipeline.stages.s2_enrich import S2Result


class TraceFlusher:
    """
    Static helper to build implicit metadata and flush embed-chain traces.

    Responsibilities:
    - ``build_implicit_meta`` — merge S0/S1/S2 artefact references and statistics
      into the dict stored on the document's ``implicit_meta`` Postgres column.
    - ``build_embed_trace_patch`` — produce the meta-patch dict that merges S6
      embed-chain traces into the existing ``implicit_meta``.
    """

    logger = loggerplusplus.bind(identifier="TraceFlusher")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        raise TypeError("TraceFlusher is a static-only class and cannot be instantiated.")

    @staticmethod
    def build_implicit_meta(
        s0_result: S0Result,
        ir: DocumentIR,
        s1_result: S1Result,
        s0_fp: str,
        s1_fp: str,
        ir_key: str,
        s2_result: S2Result | None = None,
        s2_fp: str | None = None,
    ) -> dict[str, Any]:
        """
        Assemble the implicit_meta dict for the document record update.

        Combines file-intrinsic S0 metadata with IR-derived statistics and S3 references.
        When S2 ran, enrichment stats (budget_spent, ocr_calls, vlm_calls) are included.

        Args:
            s0_result (S0Result): S0 stage output.
            ir (DocumentIR): Final IR (enriched when S2 ran, raw when S2 skipped).
            s1_result (S1Result): S1 stage output.
            s0_fp (str): S0 Merkle fingerprint.
            s1_fp (str): S1 Merkle fingerprint.
            ir_key (str): S3 key for the (pre-enrichment) DocumentIR JSON.
            s2_result (S2Result | None): S2 stage output, or None when S2 was skipped.
            s2_fp (str | None): S2 Merkle fingerprint, or None when S2 was skipped.

        Returns:
            dict: Implicit metadata dict for the document record.
        """
        meta: dict[str, Any] = {
            **s0_result.implicit_meta,
            "n_blocks": len(ir.blocks),
            "n_figures": len(ir.figure_blocks),
            "n_tables": len(ir.table_blocks),
            "s0_fingerprint": s0_fp,
            "s1_fingerprint": s1_fp,
            "ir_key": ir_key,
            "markdown_key": s1_result.markdown_key,
            # Chain lineage from S1 (parse).  Each entry is a ChainTrace dict ready for the
            # frontend to render: stage, final_provider, attempts[].  Empty when the parse
            # chain was a no-op (single provider, never escalated).
            "chain_traces": [t.model_dump() for t in ir.chain_traces],
            # Parser-side quality estimate (e.g. blocks_with_text / total_blocks).
            # Surfaced in the inspector so operators can see why a chain escalated.
            "quality_score": ir.quality_score,
        }
        if s2_result is not None and s2_fp is not None:
            meta["s2_fingerprint"] = s2_fp
            meta["budget_spent"] = s2_result.budget_spent
            meta["figures_enriched"] = s2_result.figures_processed
            meta["ocr_calls"] = s2_result.ocr_calls
            meta["vlm_calls"] = s2_result.vlm_calls
            meta["chart_extractions"] = s2_result.chart_extractions
            # Provider-call cache statistics so the UI can show how often dedup
            # saved an OCR/VLM/classifier API call across repeating crops.
            meta["ocr_cache_hits"] = s2_result.ocr_cache_hits
            meta["vlm_cache_hits"] = s2_result.vlm_cache_hits
            meta["classifier_calls"] = s2_result.classifier_calls
            meta["classifier_cache_hits"] = s2_result.classifier_cache_hits
            # Enriched IR may have ADDITIONAL chain_traces (none today, but reserve the slot
            # so a future S2-level stage trace can ride here without changing the schema).
            if ir.chain_traces:
                meta["chain_traces"] = [t.model_dump() for t in ir.chain_traces]
        return meta

    @staticmethod
    def build_embed_trace_patch(
        current_meta: dict[str, Any],
        chain_traces: list[Any],
    ) -> dict[str, Any]:
        """
        Produce an updated meta dict with S6 embed-chain traces merged in.

        Called after S6 completes to flush indexing lineage (which provider produced
        which batch) onto the document so the inspector can render it.

        Args:
            current_meta (dict): Existing ``implicit_meta`` dict from the document record.
            chain_traces (list): List of ChainTrace objects from the S6 result.

        Returns:
            dict: Updated meta dict with ``embed_chain_traces`` key added.
        """
        patched = dict(current_meta)
        patched["embed_chain_traces"] = [t.model_dump() for t in chain_traces]
        return patched

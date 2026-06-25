# ====== Code Summary ======
# FigureEnricher — processes a single FIGURE block through the S2 routing pipeline:
# classify → gate DECORATIVE → OCR → VLM → build enriched block.
# It owns the three chains + S3 + provider cache and mutates an S2Counters
# accumulator passed by the stage.  Extracted from S2EnrichStage.run to keep both the
# stage and the per-block routing under the line limit.

# ====== Standard Library Imports ======
from __future__ import annotations

import hashlib
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

from common_libs.providers.chain import Chain

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import (
    Block,
    ChainTrace,
    FigureEnrichment,
    FigureKind,
)
from common_libs.storage.s3.client import S3Client
from common_libs.pipeline.caches.provider_cache import ProviderCallCache

# ====== Local Project Imports ======
from .cache_runner import CacheRunner
from .figure_routing import FigureRoutingHelpers
from .models import S2Counters


class FigureEnricher(LoggerClass):
    """
    Routes a single FIGURE block through classifier / OCR / VLM and builds its enrichment.

    Holds the three chains plus the S3 client and the provider-call cache.
    ``process_block`` mutates the shared ``S2Counters`` accumulator and returns the updated
    block (the figure block with its accumulated chain traces and enrichment).  OCR/VLM
    routing steps are delegated to ``FigureRoutingHelpers``.
    """

    def __init__(
        self,
        classifier_chain: Chain[Any, Any],
        ocr_chain: Chain[Any, Any] | None,
        vlm_chain: Chain[Any, Any] | None,
        s3: S3Client,
        provider_cache: ProviderCallCache,
        chart_to_data: bool = False,
    ) -> None:
        """
        Wire the enricher with its three chains and infrastructure.

        Args:
            classifier_chain (Chain[Any, Any]): Ordered figure classifier chain (non-empty).
            ocr_chain (Chain[Any, Any] | None): Ordered OCR chain; None disables OCR.
            vlm_chain (Chain[Any, Any] | None): Ordered VLM chain; None disables VLM.
            s3 (S3Client): SeaweedFS client for figure crop downloads.
            provider_cache (ProviderCallCache): Cross-document provider call cache.
            chart_to_data (bool): When True, CHART figures additionally request structured
                chart-to-data extraction; when False, a CHART is treated like a normal figure
                (VLM description only). Mirrors ``EnrichConfig.chart_to_data``.
        """
        LoggerClass.__init__(self)
        self._classifier_chain = classifier_chain
        self._ocr_chain = ocr_chain
        self._vlm_chain = vlm_chain
        self._s3 = s3
        self._provider_cache = provider_cache
        self._chart_to_data = chart_to_data

    async def process_block(
        self,
        block: Block,
        doc_language: str,
        counters: S2Counters,
    ) -> Block:
        """
        Process one FIGURE block, mutating ``counters`` and returning the updated block.

        Processing order:
        1. Download crop → classify (kind + relevance).
        2. Gate DECORATIVE — skip enrichment.
        3. OCR — when the kind implies text.
        4. VLM — when the kind implies a visual description (+ chart-to-data).
        5. Build the enriched FigureEnrichment and updated block.

        Args:
            block (Block): The FIGURE block to enrich (must have a non-empty crop_key).
            doc_language (str): Document language hint passed to OCR.
            counters (S2Counters): Run-level accumulator mutated in place.

        Returns:
            Block: The updated block (enriched, or passed through with traces only).
        """
        crop_key = block.figure.crop_key  # type: ignore[union-attr]

        # 1. Download the figure crop from SeaweedFS.
        try:
            crop_bytes = await self._s3.download(crop_key)
        except Exception as exc:
            self.logger.warning(
                f"S2: could not download crop for block={block.id}: {exc} — skipping"
            )
            return block

        crop_hash = hashlib.sha256(crop_bytes).hexdigest()

        # Per-block chain trace accumulator (preserves any traces from earlier stages).
        block_traces: list[ChainTrace] = list(block.chain_traces)

        # 2. Classify — cached on crop_hash so repeated logos invoke classifier once.
        classification, cls_trace, cls_was_cache_hit = await CacheRunner.run_classify(
            self._classifier_chain, self._provider_cache, crop_bytes, crop_hash,
        )
        block_traces.append(cls_trace)
        if cls_was_cache_hit:
            counters.classifier_cache_hits += 1
        else:
            counters.classifier_calls += 1

        if classification is None:
            # No classifier could rate the figure — fall back to PHOTO with low relevance.
            kind = FigureKind.PHOTO
            relevance = 0.0
        else:
            kind = classification.kind
            relevance = classification.confidence

        # 3. Gate: DECORATIVE figures skip enrichment entirely.
        if kind == FigureKind.DECORATIVE:
            updated_figure = FigureEnrichment(
                kind=kind, crop_key=crop_key, relevance=relevance,
            )
            counters.figures_processed += 1
            self.logger.debug(f"S2: block={block.id} DECORATIVE → skipped")
            return block.model_copy(update={
                "figure": updated_figure,
                "chain_traces": block_traces,
            })

        # 4. OCR routing — applies to kinds that may contain text.
        ocr_text = await FigureRoutingHelpers.maybe_ocr(
            self._ocr_chain, self._provider_cache, kind, crop_bytes, crop_hash,
            doc_language, block_traces, counters,
        )

        # 5. VLM routing — applies to kinds that benefit from a visual description.
        description, data_table = await FigureRoutingHelpers.maybe_vlm(
            self._vlm_chain, self._provider_cache, kind, crop_bytes, crop_hash,
            ocr_text, self._chart_to_data, block_traces, counters,
        )

        # 6. Build the enriched figure block with the accumulated traces.
        updated_figure = FigureEnrichment(
            kind=kind,
            crop_key=crop_key,
            relevance=relevance,
            ocr_text=ocr_text,
            description=description,
            data_table=data_table,
        )
        counters.figures_processed += 1
        self.logger.debug(
            f"S2: block={block.id} kind={kind} "
            f"ocr={'yes' if ocr_text else 'no'} "
            f"vlm={'yes' if description else 'no'} "
            f"table={'yes' if data_table else 'no'}"
        )
        return block.model_copy(update={
            "figure": updated_figure,
            "chain_traces": block_traces,
        })


# ------------------- Public API ------------------- #
__all__ = ["FigureEnricher"]

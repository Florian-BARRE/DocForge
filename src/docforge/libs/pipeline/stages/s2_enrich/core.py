# ====== Code Summary ======
# S2EnrichStage — S2 enrichment stage: classifies figures and routes each to OCR / VLM /
# chart-to-data.  Every sub-stage is driven by a Chain[T, R] so escalation lineage is
# recorded per block.  Provider-call caching and a per-job budget cap are enforced here.
# Per-block routing is delegated to FigureEnricher (figure_enricher.py); this class owns the
# IR iteration, the run-level counter accumulator, and the fingerprint parameters.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

from libs.capabilities.chain import Chain

# ====== Internal Project Imports ======
from libs.core.ir.models import (
    Block,
    BlockType,
    DocumentIR,
)
from libs.data.storage.s3.client import S3Client
from libs.engine.provider_cache import ProviderCallCache

# ====== Local Project Imports ======
from .figure_enricher import FigureEnricher
from .models import S2Counters, S2Result


class S2EnrichStage(LoggerClass):
    """
    S2 — Figure enrichment with chain-based escalation on every sub-step.

    The classifier, OCR and VLM are all driven by ``Chain[T, R]`` instances so each
    figure carries the full lineage of every provider that touched it in
    ``Block.chain_traces``.  Per-block routing is delegated to ``FigureEnricher``.

    Budget enforcement is per-run: when ``budget_spent >= max_budget_usd``, further
    figures that would incur cost are skipped (their traces are still recorded).
    """

    def __init__(
        self,
        classifier_chain: Chain[Any, Any],
        ocr_chain: Chain[Any, Any] | None,
        vlm_chain: Chain[Any, Any] | None,
        s3: S3Client,
        provider_cache: ProviderCallCache,
        max_budget_usd: float = 0.0,
    ) -> None:
        """
        Wire the S2 stage with its three chains.

        Args:
            classifier_chain (Chain[Any, Any]):
                Ordered figure classifier chain (always non-empty).
            ocr_chain (Chain[Any, Any] | None):
                Ordered OCR chain; None disables OCR routing entirely.
            vlm_chain (Chain[Any, Any] | None):
                Ordered VLM chain; None disables VLM routing entirely.
            s3 (S3Client): SeaweedFS client for figure crop downloads.
            provider_cache (ProviderCallCache): Cross-document provider call cache.
            max_budget_usd (float): Per-job budget cap in USD.  0.0 = no limit.
        """
        LoggerClass.__init__(self)
        self._classifier_chain = classifier_chain
        self._ocr_chain = ocr_chain
        self._vlm_chain = vlm_chain
        # Convert 0.0 (sentinel = no limit) to +∞ so comparisons are uniform.
        self._max_budget = max_budget_usd if max_budget_usd > 0 else float("inf")
        self._enricher = FigureEnricher(
            classifier_chain=classifier_chain,
            ocr_chain=ocr_chain,
            vlm_chain=vlm_chain,
            s3=s3,
            provider_cache=provider_cache,
            max_budget=self._max_budget,
        )

    def params_for_fingerprint(self) -> dict[str, Any]:
        """
        Extract S2 fingerprint parameters.

        Any change to the classifier / OCR / VLM chains' signatures invalidates the
        S2 cache for all documents — downstream chunks and embeddings are also
        invalidated.

        Returns:
            dict[str, Any]: Fingerprint dict for the stage engine's Merkle-DAG.
        """
        return {
            "classifier_chain": self._classifier_chain.signature(),
            "ocr_chain": self._ocr_chain.signature() if self._ocr_chain else "none",
            "vlm_chain": self._vlm_chain.signature() if self._vlm_chain else "none",
            "max_budget_usd": (
                self._max_budget if self._max_budget != float("inf") else 0.0
            ),
        }

    async def run(self, s1: Any, ir: DocumentIR) -> S2Result:
        """
        Enrich every FIGURE block in the IR via the three chains.

        Non-FIGURE blocks (and figures without a crop_key) pass through unchanged.
        Each enrichable FIGURE block is routed through ``FigureEnricher.process_block``.

        Args:
            s1: S1Result (passed through for future cross-stage use; unused here).
            ir (DocumentIR): IR produced by S1; will be enriched in a copy.

        Returns:
            S2Result: Enriched IR plus all accounting counters for this run.
        """
        self.logger.info(
            f"S2 started: doc_id={ir.doc_id} figures={len(ir.figure_blocks)}"
        )

        # 1. Initialise the per-run accumulator and the output block list.
        counters = S2Counters()
        enriched_blocks: list[Block] = []

        # 2. Process each block — non-FIGURE / crop-less blocks pass through unchanged.
        for block in ir.blocks:
            if block.type != BlockType.FIGURE or block.figure is None or not block.figure.crop_key:
                enriched_blocks.append(block)
                continue
            enriched_blocks.append(
                await self._enricher.process_block(block, ir.language, counters)
            )

        # 3. Assemble the enriched IR and the result contract.
        enriched_ir = ir.model_copy(update={"blocks": enriched_blocks})
        result = S2Result(
            ir=enriched_ir,
            budget_spent=counters.budget_spent,
            figures_processed=counters.figures_processed,
            ocr_calls=counters.ocr_calls,
            vlm_calls=counters.vlm_calls,
            chart_extractions=counters.chart_extractions,
            ocr_cache_hits=counters.ocr_cache_hits,
            vlm_cache_hits=counters.vlm_cache_hits,
            classifier_calls=counters.classifier_calls,
            classifier_cache_hits=counters.classifier_cache_hits,
        )

        self.logger.info(
            f"S2 done: doc_id={ir.doc_id} figures={counters.figures_processed} "
            f"classifier(call/hit)={counters.classifier_calls}/{counters.classifier_cache_hits} "
            f"ocr(call/hit)={counters.ocr_calls}/{counters.ocr_cache_hits} "
            f"vlm(call/hit)={counters.vlm_calls}/{counters.vlm_cache_hits} "
            f"chart_extractions={counters.chart_extractions} "
            f"budget_spent={counters.budget_spent:.4f} USD"
        )
        return result


# ------------------- Public API ------------------- #
__all__ = ["S2EnrichStage"]

# ====== Code Summary ======
# S2EnrichStage — S2 enrichment stage: classifies figures and routes each to OCR / VLM /
# chart-to-data.  Every sub-stage is driven by a Chain[T, R] so escalation lineage is
# recorded per block.  Provider-call caching and a per-job budget cap are enforced here.

from __future__ import annotations

# ====== Standard Library Imports ======
import hashlib
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.core.ir.models import (
    Block,
    BlockType,
    ChainTrace,
    DocumentIR,
    FigureEnrichment,
    FigureKind,
)
from libs.engine.provider_cache import ProviderCallCache
from libs.capabilities.chain import Chain
from libs.data.storage.s3.client import S3Client

# ====== Local Project Imports ======
from .cache_runner import CacheRunner
from .models import S2Result


class S2EnrichStage(LoggerClass):
    """
    S2 — Figure enrichment with chain-based escalation on every sub-step.

    The classifier, OCR and VLM are all driven by ``Chain[T, R]`` instances so each
    figure carries the full lineage of every provider that touched it in
    ``Block.chain_traces``.

    Budget enforcement is per-run: when ``budget_spent >= max_budget_usd``, further
    figures that would incur cost are skipped (their traces are still recorded).
    """

    # Figure kinds that trigger OCR routing.
    _OCR_KINDS: frozenset[FigureKind] = frozenset(
        {FigureKind.SCANNED_TEXT, FigureKind.CHART, FigureKind.DIAGRAM}
    )
    # Figure kinds that trigger VLM routing.
    _VLM_KINDS: frozenset[FigureKind] = frozenset(
        {FigureKind.CHART, FigureKind.DIAGRAM, FigureKind.PHOTO}
    )

    def __init__(
        self,
        classifier_chain: "Chain[Any, Any]",
        ocr_chain: "Chain[Any, Any] | None",
        vlm_chain: "Chain[Any, Any] | None",
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
        self._s3 = s3
        self._provider_cache = provider_cache
        # Convert 0.0 (sentinel = no limit) to +∞ so comparisons are uniform.
        self._max_budget = max_budget_usd if max_budget_usd > 0 else float("inf")

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

        Processing order per block:
        1. Classify — determines the ``FigureKind`` for routing.
        2. Gate DECORATIVE — skip all enrichment for decorative figures.
        3. Gate budget — stop costly calls when the USD cap is reached.
        4. OCR — if the kind implies text (scanned text / chart / diagram).
        5. VLM — if the kind implies a visual description (chart / diagram / photo).
        6. Build the enriched ``FigureEnrichment`` and updated block.

        Args:
            s1: S1Result (passed through for future cross-stage use; unused here).
            ir (DocumentIR): IR produced by S1; will be enriched in a copy.

        Returns:
            S2Result: Enriched IR plus all accounting counters for this run.
        """
        self.logger.info(
            f"S2 started: doc_id={ir.doc_id} figures={len(ir.figure_blocks)}"
        )

        # 1. Initialise per-run accumulators.
        budget_spent: float = 0.0
        figures_processed: int = 0
        ocr_calls: int = 0
        vlm_calls: int = 0
        chart_extractions: int = 0
        ocr_cache_hits: int = 0
        vlm_cache_hits: int = 0
        classifier_calls: int = 0
        classifier_cache_hits: int = 0

        enriched_blocks: list[Block] = []

        # 2. Process each block — non-FIGURE blocks pass through unchanged.
        for block in ir.blocks:
            if block.type != BlockType.FIGURE or block.figure is None:
                enriched_blocks.append(block)
                continue

            crop_key = block.figure.crop_key
            if not crop_key:
                enriched_blocks.append(block)
                continue

            # 3. Download the figure crop from SeaweedFS.
            try:
                crop_bytes = await self._s3.download(crop_key)
            except Exception as exc:
                self.logger.warning(
                    f"S2: could not download crop for block={block.id}: {exc} — skipping"
                )
                enriched_blocks.append(block)
                continue

            crop_hash = hashlib.sha256(crop_bytes).hexdigest()

            # Per-block chain trace accumulator (preserves any traces from earlier stages).
            block_traces: list[ChainTrace] = list(block.chain_traces)

            # 4. Classify — cached on crop_hash so repeated logos invoke classifier once.
            classification, cls_trace, cls_was_cache_hit = await CacheRunner.run_classify(
                self._classifier_chain, self._provider_cache, crop_bytes, crop_hash,
            )
            block_traces.append(cls_trace)
            if cls_was_cache_hit:
                classifier_cache_hits += 1
            else:
                classifier_calls += 1

            if classification is None:
                # No classifier could rate the figure — fall back to PHOTO with low relevance.
                kind = FigureKind.PHOTO
                relevance = 0.0
            else:
                kind = classification.kind
                relevance = classification.confidence

            # 5. Gate: DECORATIVE figures skip enrichment entirely.
            if kind == FigureKind.DECORATIVE:
                updated_figure = FigureEnrichment(
                    kind=kind, crop_key=crop_key, relevance=relevance,
                )
                enriched_blocks.append(block.model_copy(update={
                    "figure": updated_figure,
                    "chain_traces": block_traces,
                }))
                figures_processed += 1
                self.logger.debug(f"S2: block={block.id} DECORATIVE → skipped")
                continue

            # 6. Gate: budget cap — stop costly API calls when limit is reached.
            if budget_spent >= self._max_budget:
                self.logger.warning(
                    f"S2: budget exhausted (spent={budget_spent:.4f} >= "
                    f"max={self._max_budget:.4f}) — skipping block={block.id}"
                )
                enriched_blocks.append(block.model_copy(update={
                    "chain_traces": block_traces,
                }))
                continue

            # 7. OCR routing — applies to kinds that may contain text.
            ocr_text: str | None = None
            if self._ocr_chain and kind in self._OCR_KINDS:
                ocr_result, call_cost, ocr_trace, ocr_was_cache_hit = await CacheRunner.run_ocr(
                    self._ocr_chain, self._provider_cache,
                    crop_bytes, crop_hash, ir.language,
                )
                block_traces.append(ocr_trace)
                if ocr_result is not None:
                    ocr_text = ocr_result.text if ocr_result.text.strip() else None
                    budget_spent += call_cost
                    if ocr_was_cache_hit:
                        ocr_cache_hits += 1
                    else:
                        ocr_calls += 1

            # 8. VLM routing — applies to kinds that benefit from a visual description.
            description: str | None = None
            data_table: list[list[str]] | None = None

            if self._vlm_chain and kind in self._VLM_KINDS:
                remaining = self._max_budget - budget_spent
                if remaining > 0:
                    use_chart_schema = kind == FigureKind.CHART
                    vlm_result, vlm_cost, vlm_trace, vlm_was_cache_hit = await CacheRunner.run_vlm(
                        self._vlm_chain, self._provider_cache,
                        crop_bytes, crop_hash, ocr_text, use_chart_schema,
                    )
                    block_traces.append(vlm_trace)
                    if vlm_result is not None:
                        description = vlm_result.description or None
                        budget_spent += vlm_cost
                        if vlm_was_cache_hit:
                            vlm_cache_hits += 1
                        else:
                            vlm_calls += 1

                        # Chart-to-data: extract a structured table from the VLM output.
                        if use_chart_schema and vlm_result.structured:
                            raw_table = vlm_result.structured.get("table")
                            if raw_table and isinstance(raw_table, list):
                                data_table = [
                                    [str(cell) for cell in row]
                                    for row in raw_table
                                    if isinstance(row, list)
                                ]
                                if data_table:
                                    chart_extractions += 1

            # 9. Build the enriched figure block with the accumulated traces.
            updated_figure = FigureEnrichment(
                kind=kind,
                crop_key=crop_key,
                relevance=relevance,
                ocr_text=ocr_text,
                description=description,
                data_table=data_table,
            )
            enriched_blocks.append(block.model_copy(update={
                "figure": updated_figure,
                "chain_traces": block_traces,
            }))
            figures_processed += 1

            self.logger.debug(
                f"S2: block={block.id} kind={kind} "
                f"ocr={'yes' if ocr_text else 'no'} "
                f"vlm={'yes' if description else 'no'} "
                f"table={'yes' if data_table else 'no'}"
            )

        enriched_ir = ir.model_copy(update={"blocks": enriched_blocks})

        result = S2Result(
            ir=enriched_ir,
            budget_spent=budget_spent,
            figures_processed=figures_processed,
            ocr_calls=ocr_calls,
            vlm_calls=vlm_calls,
            chart_extractions=chart_extractions,
            ocr_cache_hits=ocr_cache_hits,
            vlm_cache_hits=vlm_cache_hits,
            classifier_calls=classifier_calls,
            classifier_cache_hits=classifier_cache_hits,
        )

        self.logger.info(
            f"S2 done: doc_id={ir.doc_id} figures={figures_processed} "
            f"classifier(call/hit)={classifier_calls}/{classifier_cache_hits} "
            f"ocr(call/hit)={ocr_calls}/{ocr_cache_hits} "
            f"vlm(call/hit)={vlm_calls}/{vlm_cache_hits} "
            f"chart_extractions={chart_extractions} "
            f"budget_spent={budget_spent:.4f} USD"
        )
        return result


# ------------------- Public API ------------------- #
__all__ = ["S2EnrichStage"]

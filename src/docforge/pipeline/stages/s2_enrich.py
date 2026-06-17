# ====== Code Summary ======
# S2 — Enrichment stage: classifies figures and routes each to OCR / VLM / chart-to-data.
# Integrates the provider-call cache (cross-document dedup) and a per-job budget cap.
# Modifies the DocumentIR in-place on the Pydantic level (model_copy for immutability).

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from loggerplusplus import LoggerClass

from ir.models import Block, BlockType, DocumentIR, FigureEnrichment, FigureKind
from pipeline.provider_cache import ProviderCallCache
from providers.chain import ProviderChain
from providers.classifier.base import FigureClassifier
from providers.interfaces import OcrHint, OcrResult, VlmResult
from storage.s3.client import S3Client

from .s1_parse import S1Result


@dataclass(slots=True)
class S2Result:
    """
    Output of the S2 enrichment stage.

    Carries the enriched DocumentIR (figure blocks updated with OCR text, VLM description,
    and chart-to-data extractions) along with cost and call statistics.
    """

    ir: DocumentIR                 # Enriched IR: figure.ocr_text / .description / .data_table filled
    budget_spent: float            # Total OCR + VLM API cost in USD for this run
    figures_processed: int         # Number of FIGURE blocks that went through enrichment routing
    ocr_calls: int                 # Number of OCR provider calls (cache misses only)
    vlm_calls: int                 # Number of VLM provider calls (cache misses only)
    chart_extractions: int         # Number of figures where chart-to-data produced a data_table


class S2EnrichStage(LoggerClass):
    """
    S2 — Figure enrichment stage with per-element routing.

    Responsibilities:
    1. For each FIGURE block in the IR: download the crop from SeaweedFS.
    2. Classify the figure (LayoutLabels or ViT ONNX) → FigureKind.
    3. Route based on kind:
       - DECORATIVE   → skip (no OCR, no VLM)
       - SCANNED_TEXT → OCR only
       - CHART        → OCR + VLM description (grounded) + chart-to-data
       - DIAGRAM      → OCR + VLM description (grounded)
       - PHOTO        → VLM description only
    4. All OCR/VLM calls go through the provider-call cache (cross-document dedup).
    5. Budget cap: if max_budget_usd > 0, skip enrichment when the budget is exhausted.
    6. Return an enriched IR with updated FigureEnrichment slots.
    """

    # OCR routing: kinds that benefit from text extraction
    _OCR_KINDS: frozenset[FigureKind] = frozenset(
        {FigureKind.SCANNED_TEXT, FigureKind.CHART, FigureKind.DIAGRAM}
    )

    # VLM routing: kinds that benefit from visual description
    _VLM_KINDS: frozenset[FigureKind] = frozenset(
        {FigureKind.CHART, FigureKind.DIAGRAM, FigureKind.PHOTO}
    )

    def __init__(
        self,
        classifier: FigureClassifier,
        ocr_chain: ProviderChain | None,
        vlm_chain: ProviderChain | None,
        s3: S3Client,
        provider_cache: ProviderCallCache,
        max_budget_usd: float = 0.0,
    ) -> None:
        """
        Initialize the enrichment stage.

        Args:
            classifier (FigureClassifier): Figure kind classifier (layout or ViT).
            ocr_chain (ProviderChain | None): Ordered OCR providers with escalation.
                None disables OCR entirely for this stage.
            vlm_chain (ProviderChain | None): Ordered VLM providers with escalation.
                None disables VLM entirely for this stage.
            s3 (S3Client): SeaweedFS client for downloading figure crops.
            provider_cache (ProviderCallCache): Cross-document provider call cache.
            max_budget_usd (float): Per-job budget cap in USD.  0.0 = no limit.
        """
        LoggerClass.__init__(self)
        self._classifier = classifier
        self._ocr_chain = ocr_chain
        self._vlm_chain = vlm_chain
        self._s3 = s3
        self._provider_cache = provider_cache
        self._max_budget = max_budget_usd if max_budget_usd > 0 else float("inf")

    def params_for_fingerprint(self) -> dict[str, Any]:
        """
        Extract S2 fingerprint parameters.

        Any change to classifier, OCR chain, or VLM chain invalidates the S2 cache
        for all documents — downstream chunks and embeddings are also invalidated.
        """
        return {
            "classifier_name": getattr(self._classifier, "name", "unknown"),
            "classifier_version": getattr(self._classifier, "version", "0"),
            "ocr_chain": (
                self._ocr_chain.provider_chain_signature()
                if self._ocr_chain else "none"
            ),
            "vlm_chain": (
                self._vlm_chain.provider_chain_signature()
                if self._vlm_chain else "none"
            ),
            "max_budget_usd": self._max_budget if self._max_budget != float("inf") else 0.0,
        }

    async def run(self, s1: S1Result, ir: DocumentIR) -> S2Result:
        """
        Enrich all FIGURE blocks in the IR.

        Args:
            s1 (S1Result): S1 output (provides figure_crop_keys for batch context).
            ir (DocumentIR): Parsed DocumentIR from S1 (blocks with crop_key set).

        Returns:
            S2Result: Enriched IR with updated FigureEnrichment slots and cost stats.
        """
        self.logger.info(
            f"S2 started: doc_id={ir.doc_id} "
            f"figures={len(ir.figure_blocks)}"
        )

        budget_spent: float = 0.0
        figures_processed: int = 0
        ocr_calls: int = 0
        vlm_calls: int = 0
        chart_extractions: int = 0

        enriched_blocks: list[Block] = []

        for block in ir.blocks:
            # 1. Only FIGURE blocks are enriched; all others pass through unchanged
            if block.type != BlockType.FIGURE or block.figure is None:
                enriched_blocks.append(block)
                continue

            crop_key = block.figure.crop_key
            if not crop_key:
                # Figure has no crop (parser couldn't extract bbox) → skip
                enriched_blocks.append(block)
                continue

            # 2. Download the crop image from SeaweedFS
            try:
                crop_bytes = await self._s3.download(crop_key)
            except Exception as exc:
                self.logger.warning(
                    f"S2: could not download crop for block={block.id}: {exc} — skipping"
                )
                enriched_blocks.append(block)
                continue

            crop_hash = hashlib.sha256(crop_bytes).hexdigest()

            # 3. Classify the figure kind
            classification = await self._classifier.classify(crop_bytes)
            kind = classification.kind
            relevance = classification.confidence

            # 4. DECORATIVE → skip enrichment entirely (gate)
            if kind == FigureKind.DECORATIVE:
                updated_figure = FigureEnrichment(
                    kind=kind,
                    crop_key=crop_key,
                    relevance=relevance,
                )
                enriched_blocks.append(block.model_copy(update={"figure": updated_figure}))
                figures_processed += 1
                self.logger.debug(f"S2: block={block.id} DECORATIVE → skipped")
                continue

            # 5. Budget gate — skip expensive calls when budget exhausted
            if budget_spent >= self._max_budget:
                self.logger.warning(
                    f"S2: budget exhausted (spent={budget_spent:.4f} >= max={self._max_budget:.4f})"
                    f" — skipping block={block.id}"
                )
                enriched_blocks.append(block)
                continue

            # 6. OCR routing
            ocr_text: str | None = None
            if self._ocr_chain and kind in self._OCR_KINDS:
                cached_ocr, call_cost = await self._cached_ocr(
                    crop_bytes, crop_hash, ir.language
                )
                if cached_ocr is not None:
                    ocr_text = cached_ocr.text if cached_ocr.text.strip() else None
                    budget_spent += call_cost
                    if call_cost > 0:  # Only count non-cached calls
                        ocr_calls += 1

            # 7. VLM routing
            description: str | None = None
            data_table: list[list[str]] | None = None

            if self._vlm_chain and kind in self._VLM_KINDS:
                remaining = self._max_budget - budget_spent
                if remaining > 0:
                    use_chart_schema = kind == FigureKind.CHART
                    cached_vlm, vlm_cost = await self._cached_vlm(
                        crop_bytes, crop_hash, ocr_text, use_chart_schema
                    )
                    if cached_vlm is not None:
                        description = cached_vlm.description or None
                        budget_spent += vlm_cost
                        if vlm_cost > 0:
                            vlm_calls += 1

                        # 8. Chart-to-data: extract table from structured VLM output
                        if use_chart_schema and cached_vlm.structured:
                            raw_table = cached_vlm.structured.get("table")
                            if raw_table and isinstance(raw_table, list):
                                data_table = [
                                    [str(cell) for cell in row]
                                    for row in raw_table
                                    if isinstance(row, list)
                                ]
                                if data_table:
                                    chart_extractions += 1

            # 9. Build updated FigureEnrichment
            updated_figure = FigureEnrichment(
                kind=kind,
                crop_key=crop_key,
                relevance=relevance,
                ocr_text=ocr_text,
                description=description,
                data_table=data_table,
            )
            enriched_blocks.append(block.model_copy(update={"figure": updated_figure}))
            figures_processed += 1

            self.logger.debug(
                f"S2: block={block.id} kind={kind} "
                f"ocr={'yes' if ocr_text else 'no'} "
                f"vlm={'yes' if description else 'no'} "
                f"table={'yes' if data_table else 'no'}"
            )

        # 10. Build enriched IR (immutable update via model_copy)
        enriched_ir = ir.model_copy(update={"blocks": enriched_blocks})

        result = S2Result(
            ir=enriched_ir,
            budget_spent=budget_spent,
            figures_processed=figures_processed,
            ocr_calls=ocr_calls,
            vlm_calls=vlm_calls,
            chart_extractions=chart_extractions,
        )

        self.logger.info(
            f"S2 done: doc_id={ir.doc_id} "
            f"figures={figures_processed} "
            f"ocr_calls={ocr_calls} vlm_calls={vlm_calls} "
            f"chart_extractions={chart_extractions} "
            f"budget_spent={budget_spent:.4f} USD"
        )
        return result

    # ─── Provider-call cache helpers ──────────────────────────────────────────

    async def _cached_ocr(
        self,
        crop_bytes: bytes,
        crop_hash: str,
        doc_language: str,
    ) -> tuple[OcrResult | None, float]:
        """
        Run OCR through the chain, consulting the provider-call cache first.

        Returns (OcrResult | None, cost_incurred).
        cost_incurred is 0.0 on a cache hit (no API call made).
        """
        if self._ocr_chain is None:
            return None, 0.0

        # OCR params: language hint (affects model behaviour)
        params = {"language": doc_language}
        first_provider = (
            self._ocr_chain.providers[0] if self._ocr_chain.providers else None
        )
        if first_provider is None:
            return None, 0.0

        call_fp = ProviderCallCache.compute_key(
            capability="ocr",
            provider_id=getattr(first_provider, "name", "ocr"),
            provider_version=getattr(first_provider, "version", "0"),
            params=params,
            content_hash=crop_hash,
        )

        # 1. Cache lookup
        cached_raw = await self._provider_cache.get(call_fp)
        if cached_raw is not None:
            self.logger.debug(f"OCR provider-call cache HIT: {call_fp[:12]}…")
            return OcrResult.model_validate_json(cached_raw), 0.0

        # 2. Cache miss — call the chain
        hint = OcrHint(language=doc_language)
        result: OcrResult | None = await self._ocr_chain.call(
            lambda p: p.extract(crop_bytes, hint)
        )

        if result is None:
            return None, 0.0

        # 3. Compute cost (sum of cost_per_page for the first provider that succeeded)
        cost = getattr(first_provider, "cost_per_page", 0.0)

        # 4. Cache the result
        await self._provider_cache.put(
            call_fp=call_fp,
            capability="ocr",
            provider_id=getattr(first_provider, "name", "ocr"),
            provider_version=getattr(first_provider, "version", "0"),
            content_hash=crop_hash,
            result_json=result.model_dump_json(),
            cost=cost,
        )

        return result, cost

    async def _cached_vlm(
        self,
        crop_bytes: bytes,
        crop_hash: str,
        ocr_text: str | None,
        use_chart_schema: bool,
    ) -> tuple[VlmResult | None, float]:
        """
        Run VLM description through the chain, consulting the provider-call cache first.

        Returns (VlmResult | None, cost_incurred).
        """
        if self._vlm_chain is None:
            return None, 0.0

        first_provider = (
            self._vlm_chain.providers[0] if self._vlm_chain.providers else None
        )
        if first_provider is None:
            return None, 0.0

        params = {
            "grounding": bool(ocr_text),
            "chart_schema": use_chart_schema,
        }
        call_fp = ProviderCallCache.compute_key(
            capability="vlm",
            provider_id=getattr(first_provider, "name", "vlm"),
            provider_version=getattr(first_provider, "version", "0"),
            params=params,
            content_hash=crop_hash,
        )

        # 1. Cache lookup
        cached_raw = await self._provider_cache.get(call_fp)
        if cached_raw is not None:
            self.logger.debug(f"VLM provider-call cache HIT: {call_fp[:12]}…")
            return VlmResult.model_validate_json(cached_raw), 0.0

        # 2. Cache miss — call the chain
        from providers.vlm import OpenAICompatVlmProvider
        schema = (
            OpenAICompatVlmProvider.chart_schema()
            if use_chart_schema and isinstance(first_provider, OpenAICompatVlmProvider)
            else None
        )

        result: VlmResult | None = await self._vlm_chain.call(
            lambda p: p.describe(crop_bytes, grounding=ocr_text, schema=schema)
        )

        if result is None:
            return None, 0.0

        # 3. Compute cost
        cost = getattr(first_provider, "cost_per_call", 0.0)

        # 4. Cache the result
        await self._provider_cache.put(
            call_fp=call_fp,
            capability="vlm",
            provider_id=getattr(first_provider, "name", "vlm"),
            provider_version=getattr(first_provider, "version", "0"),
            content_hash=crop_hash,
            result_json=result.model_dump_json(),
            cost=cost,
        )

        return result, cost

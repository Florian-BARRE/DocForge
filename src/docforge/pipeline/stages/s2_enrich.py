# ====== Code Summary ======
# S2 — Enrichment stage: classifies figures and routes each to OCR / VLM / chart-to-data.
# Every sub-stage (classifier, OCR, VLM) is a Chain[T, R] so every escalation step is
# recorded; the per-figure chain traces are appended to the figure's Block.chain_traces.
# The provider-call cache (cross-document dedup) and a per-job budget cap are unchanged.

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from loggerplusplus import LoggerClass

from ir.models import (
    Block, BlockType, ChainAttemptIR, ChainTrace, DocumentIR,
    FigureEnrichment, FigureKind,
)
from pipeline.provider_cache import ProviderCallCache
from providers.chain import Chain, ChainOutcome, chain_outcome_to_attempt_dicts
from providers.classifier.base import ClassificationResult
from providers.interfaces import OcrHint, OcrResult, VlmResult
from storage.s3.client import S3Client

from .s1_parse import S1Result


@dataclass(slots=True)
class S2Result:
    """Output of the S2 enrichment stage (counts + the enriched IR)."""

    ir: DocumentIR
    budget_spent: float
    figures_processed: int
    ocr_calls: int
    vlm_calls: int
    chart_extractions: int
    # ─── Cache-aware counters (Phase A) ─────────────────────────────────
    # Hits = a duplicate crop was answered from ProviderCallCache without
    # invoking the underlying chain (zero API cost, zero latency).  Misses
    # = the chain ran.  ocr_calls / vlm_calls above remain the miss counts
    # (== number of chain invocations) for backward compatibility.
    ocr_cache_hits: int = 0
    vlm_cache_hits: int = 0
    classifier_calls: int = 0
    classifier_cache_hits: int = 0


class S2EnrichStage(LoggerClass):
    """
    S2 — Figure enrichment with chain-based escalation on every sub-step.

    The classifier, OCR and VLM are all driven by ``Chain[T, R]`` instances so each
    figure carries the full lineage of every provider that touched it in
    ``Block.chain_traces``.
    """

    _OCR_KINDS: frozenset[FigureKind] = frozenset(
        {FigureKind.SCANNED_TEXT, FigureKind.CHART, FigureKind.DIAGRAM}
    )
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
            classifier_chain (Chain[FigureClassifier, ClassificationResult]):
                Ordered figure classifier chain (always non-empty).
            ocr_chain (Chain[OcrProvider, OcrResult] | None):
                Ordered OCR chain; None disables OCR routing entirely.
            vlm_chain (Chain[VlmProvider, VlmResult] | None):
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
        self._max_budget = max_budget_usd if max_budget_usd > 0 else float("inf")

    def params_for_fingerprint(self) -> dict[str, Any]:
        """
        Extract S2 fingerprint parameters.

        Any change to the classifier / OCR / VLM chains' signatures invalidates the
        S2 cache for all documents — downstream chunks and embeddings are also
        invalidated.
        """
        return {
            "classifier_chain": self._classifier_chain.signature(),
            "ocr_chain": self._ocr_chain.signature() if self._ocr_chain else "none",
            "vlm_chain": self._vlm_chain.signature() if self._vlm_chain else "none",
            "max_budget_usd": (
                self._max_budget if self._max_budget != float("inf") else 0.0
            ),
        }

    async def run(self, s1: S1Result, ir: DocumentIR) -> S2Result:
        """Enrich every FIGURE block in the IR via the three chains."""
        self.logger.info(
            f"S2 started: doc_id={ir.doc_id} figures={len(ir.figure_blocks)}"
        )

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

        for block in ir.blocks:
            if block.type != BlockType.FIGURE or block.figure is None:
                enriched_blocks.append(block)
                continue

            crop_key = block.figure.crop_key
            if not crop_key:
                enriched_blocks.append(block)
                continue

            try:
                crop_bytes = await self._s3.download(crop_key)
            except Exception as exc:
                self.logger.warning(
                    f"S2: could not download crop for block={block.id}: {exc} — skipping"
                )
                enriched_blocks.append(block)
                continue

            crop_hash = hashlib.sha256(crop_bytes).hexdigest()

            # Per-block chain trace accumulator
            block_traces: list[ChainTrace] = list(block.chain_traces)

            # 1. Classify the figure via the classifier chain — cached on crop_hash
            #    so a logo / page header that repeats across slides only invokes the
            #    classifier once for the whole document set.
            classification, cls_trace, cls_was_cache_hit = await self._cached_classify(
                crop_bytes, crop_hash,
            )
            block_traces.append(cls_trace)
            if cls_was_cache_hit:
                classifier_cache_hits += 1
            else:
                classifier_calls += 1

            if classification is None:
                # No classifier could rate the figure — fall back to PHOTO with low relevance
                kind = FigureKind.PHOTO
                relevance = 0.0
            else:
                kind = classification.kind
                relevance = classification.confidence

            # 2. DECORATIVE → skip enrichment entirely (gate).
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

            # 3. Budget gate.
            if budget_spent >= self._max_budget:
                self.logger.warning(
                    f"S2: budget exhausted (spent={budget_spent:.4f} >= "
                    f"max={self._max_budget:.4f}) — skipping block={block.id}"
                )
                enriched_blocks.append(block.model_copy(update={
                    "chain_traces": block_traces,
                }))
                continue

            # 4. OCR routing.
            ocr_text: str | None = None
            if self._ocr_chain and kind in self._OCR_KINDS:
                cached_ocr, call_cost, ocr_trace, ocr_was_cache_hit = await self._cached_ocr(
                    crop_bytes, crop_hash, ir.language
                )
                block_traces.append(ocr_trace)
                if cached_ocr is not None:
                    ocr_text = cached_ocr.text if cached_ocr.text.strip() else None
                    budget_spent += call_cost
                    if ocr_was_cache_hit:
                        ocr_cache_hits += 1
                    else:
                        # Chain ran — either paid (call_cost > 0) or local/free.
                        ocr_calls += 1

            # 5. VLM routing.
            description: str | None = None
            data_table: list[list[str]] | None = None

            if self._vlm_chain and kind in self._VLM_KINDS:
                remaining = self._max_budget - budget_spent
                if remaining > 0:
                    use_chart_schema = kind == FigureKind.CHART
                    cached_vlm, vlm_cost, vlm_trace, vlm_was_cache_hit = await self._cached_vlm(
                        crop_bytes, crop_hash, ocr_text, use_chart_schema
                    )
                    block_traces.append(vlm_trace)
                    if cached_vlm is not None:
                        description = cached_vlm.description or None
                        budget_spent += vlm_cost
                        if vlm_was_cache_hit:
                            vlm_cache_hits += 1
                        else:
                            vlm_calls += 1

                        # Chart-to-data: extract structured table from VLM output.
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

            # 6. Build the enriched figure block with the accumulated traces.
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

    # ─── Provider-call cache helpers (one per stage) ──────────────────────────

    async def _cached_ocr(
        self,
        crop_bytes: bytes,
        crop_hash: str,
        doc_language: str,
    ) -> tuple[OcrResult | None, float, ChainTrace, bool]:
        """
        Run OCR through the chain, consulting the provider-call cache first.

        Returns:
            tuple: ``(OcrResult | None, cost_incurred, ChainTrace, was_cache_hit)``.
                The trace is always present — a cache hit emits a synthetic trace
                whose final_provider is ``"cache"`` so block-level lineage shows
                "result was served from the provider-call cache" and operators can
                see how often dedup saved an API call.
        """
        if self._ocr_chain is None:
            return None, 0.0, self._skip_trace("ocr", "no chain"), False

        params = {"language": doc_language}
        first_provider = (
            self._ocr_chain.providers[0] if self._ocr_chain.providers else None
        )
        if first_provider is None:
            return None, 0.0, self._skip_trace("ocr", "no provider"), False

        provider_id = getattr(first_provider, "name", "ocr")
        provider_version = getattr(first_provider, "version", "0")
        call_fp = ProviderCallCache.compute_key(
            capability="ocr",
            provider_id=provider_id,
            provider_version=provider_version,
            params=params,
            content_hash=crop_hash,
        )

        cached_raw = await self._provider_cache.get(call_fp)
        if cached_raw is not None:
            self.logger.debug(f"OCR provider-call cache HIT: {call_fp[:12]}…")
            return (
                OcrResult.model_validate_json(cached_raw),
                0.0,
                self._cache_hit_trace("ocr", provider_id, call_fp),
                True,
            )

        hint = OcrHint(language=doc_language)
        outcome = await self._ocr_chain.call(
            lambda p: p.extract(crop_bytes, hint)
        )
        trace = self._trace_from_outcome("ocr", outcome)

        if outcome.result is None:
            return None, 0.0, trace, False

        cost = getattr(first_provider, "cost_per_page", 0.0)
        await self._provider_cache.put(
            call_fp=call_fp,
            capability="ocr",
            provider_id=provider_id,
            provider_version=provider_version,
            content_hash=crop_hash,
            result_json=outcome.result.model_dump_json(),
            cost=cost,
        )
        return outcome.result, cost, trace, False

    async def _cached_vlm(
        self,
        crop_bytes: bytes,
        crop_hash: str,
        ocr_text: str | None,
        use_chart_schema: bool,
    ) -> tuple[VlmResult | None, float, ChainTrace, bool]:
        """
        Run VLM description through the chain, consulting the provider-call cache first.

        Returns:
            tuple: ``(VlmResult | None, cost_incurred, ChainTrace, was_cache_hit)``.
        """
        if self._vlm_chain is None:
            return None, 0.0, self._skip_trace("vlm", "no chain"), False

        first_provider = (
            self._vlm_chain.providers[0] if self._vlm_chain.providers else None
        )
        if first_provider is None:
            return None, 0.0, self._skip_trace("vlm", "no provider"), False

        provider_id = getattr(first_provider, "name", "vlm")
        provider_version = getattr(first_provider, "version", "0")
        params = {"grounding": bool(ocr_text), "chart_schema": use_chart_schema}
        call_fp = ProviderCallCache.compute_key(
            capability="vlm",
            provider_id=provider_id,
            provider_version=provider_version,
            params=params,
            content_hash=crop_hash,
        )

        cached_raw = await self._provider_cache.get(call_fp)
        if cached_raw is not None:
            self.logger.debug(f"VLM provider-call cache HIT: {call_fp[:12]}…")
            return (
                VlmResult.model_validate_json(cached_raw),
                0.0,
                self._cache_hit_trace("vlm", provider_id, call_fp),
                True,
            )

        from providers.vlm import OpenAICompatVlmProvider
        schema = (
            OpenAICompatVlmProvider.chart_schema()
            if use_chart_schema and isinstance(first_provider, OpenAICompatVlmProvider)
            else None
        )

        outcome = await self._vlm_chain.call(
            lambda p: p.describe(crop_bytes, grounding=ocr_text, schema=schema)
        )
        trace = self._trace_from_outcome("vlm", outcome)

        if outcome.result is None:
            return None, 0.0, trace, False

        cost = getattr(first_provider, "cost_per_call", 0.0)
        await self._provider_cache.put(
            call_fp=call_fp,
            capability="vlm",
            provider_id=provider_id,
            provider_version=provider_version,
            content_hash=crop_hash,
            result_json=outcome.result.model_dump_json(),
            cost=cost,
        )
        return outcome.result, cost, trace, False

    async def _cached_classify(
        self,
        crop_bytes: bytes,
        crop_hash: str,
    ) -> tuple[ClassificationResult | None, ChainTrace, bool]:
        """
        Classify a figure through the classifier chain, dedup-ing across identical crops.

        Like OCR/VLM caching, the classifier output is keyed by ``crop_hash`` so a
        repeating logo or header runs the classifier model exactly once across every
        document that contains it.  Cheap for layout_labels (heuristic) but a serious
        saving for vit_onnx (ONNX inference per crop).

        Returns:
            tuple: ``(ClassificationResult | None, ChainTrace, was_cache_hit)``.
        """
        first_provider = (
            self._classifier_chain.providers[0] if self._classifier_chain.providers else None
        )
        if first_provider is None:
            return None, self._skip_trace("classifier", "no provider"), False

        provider_id = getattr(first_provider, "name", "classifier")
        provider_version = getattr(first_provider, "version", "0")
        call_fp = ProviderCallCache.compute_key(
            capability="classifier",
            provider_id=provider_id,
            provider_version=provider_version,
            params={},
            content_hash=crop_hash,
        )

        cached_raw = await self._provider_cache.get(call_fp)
        if cached_raw is not None:
            self.logger.debug(f"Classifier cache HIT: {call_fp[:12]}…")
            # ClassificationResult is a slotted dataclass — round-trip via JSON dict.
            import json
            data = json.loads(cached_raw)
            return (
                ClassificationResult(
                    kind=FigureKind(data["kind"]),
                    confidence=float(data["confidence"]),
                ),
                self._cache_hit_trace("classifier", provider_id, call_fp),
                True,
            )

        outcome = await self._classifier_chain.call(lambda p: p.classify(crop_bytes))
        trace = self._trace_from_outcome("classifier", outcome)
        if outcome.result is None:
            return None, trace, False

        # Persist for next identical crop.  ClassificationResult is a dataclass,
        # serialise minimally — kind name + confidence.
        await self._provider_cache.put(
            call_fp=call_fp,
            capability="classifier",
            provider_id=provider_id,
            provider_version=provider_version,
            content_hash=crop_hash,
            result_json=f'{{"kind": "{outcome.result.kind.value}", "confidence": {outcome.result.confidence}}}',
            cost=0.0,
        )
        return outcome.result, trace, False

    # ─── Synthetic ChainTrace helpers ───────────────────────────────────────

    @staticmethod
    def _cache_hit_trace(stage: str, provider_id: str, call_fp: str) -> ChainTrace:
        """
        Build a synthetic ChainTrace describing a provider-call cache hit.

        We model the cache as a degenerate "provider" so the existing UI doesn't
        need a new shape: one attempt with provider_id="provider_cache" + a
        success badge, duration=0, cost=0.  The original chain's first provider
        id is carried in the attempt's ``error`` slot (renamed-ish) so the UI
        can show "cache hit (would have called paddle_ocr)".
        """
        return ChainTrace(
            stage=stage,
            attempts=[ChainAttemptIR(
                provider_id="provider_cache",
                score=1.0,
                duration_ms=0,
                succeeded=True,
                escalated=False,
                error=f"cache hit — would have called {provider_id} (fp={call_fp[:12]}…)",
                cost_usd=0.0,
            )],
            final_provider="provider_cache",
        )

    @staticmethod
    def _skip_trace(stage: str, reason: str) -> ChainTrace:
        """ChainTrace describing a sub-stage that was skipped (no chain / no provider)."""
        return ChainTrace(
            stage=stage,
            attempts=[ChainAttemptIR(
                provider_id="skip",
                score=None,
                duration_ms=0,
                succeeded=False,
                escalated=False,
                error=reason,
                cost_usd=0.0,
            )],
            final_provider=None,
        )

    # ─── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _trace_from_outcome(stage: str, outcome: "ChainOutcome[Any]") -> ChainTrace:
        """Convert a ChainOutcome into the IR ChainTrace serialisation."""
        return ChainTrace(
            stage=stage,
            attempts=[ChainAttemptIR(**d) for d in chain_outcome_to_attempt_dicts(outcome)],
            final_provider=outcome.final_provider,
        )

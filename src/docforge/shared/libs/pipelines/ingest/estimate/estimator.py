# ====== Code Summary ======
# CostEstimator — the pure heart of the pre-hoc preview: given a CostPlan (which stages spend, with
# what provider), aggregated SampleStats (pages/text/images over the covered documents), a RateTable
# and the surfaced EstimateAssumptions, it projects a per-stage token/cost breakdown plus the material
# volume (chunks, vectors, storage). It reads NO database, network or config — every input is passed
# in — so it obeys the pipeline-purity invariant and is exhaustively testable across pipeline shapes.
# A stage whose provider is local prices 0 (known); a paid provider with no known rate prices None
# (usage still reported), and the rolled-up total flags itself incomplete rather than fabricating.

# ====== Standard Library Imports ======
import math

# ====== Local Project Imports ======
from .models import CostEstimate, EstimateAssumptions, SampleStats, StageEstimate, VolumeEstimate
from .plan import CostPlan, ProviderRef
from .rates import LOCAL_FREE_KINDS, RateTable


class CostEstimator:
    """Static, pure estimator: (plan, sampled stats, rates, assumptions) → CostEstimate."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CostEstimator is a static-only class and cannot be instantiated.")

    @classmethod
    def estimate(
        cls,
        plan: CostPlan,
        stats: SampleStats,
        rates: RateTable,
        assumptions: EstimateAssumptions,
    ) -> CostEstimate:
        """
        Project the full cost/volume breakdown for a pipeline over the sampled documents.

        Args:
            plan (CostPlan): The cost-incurring stages and their providers.
            stats (SampleStats): Aggregated document statistics (scaled up when sampled).
            rates (RateTable): The rate model to price against.
            assumptions (EstimateAssumptions): The surfaced extrapolation assumptions.

        Returns:
            CostEstimate: Per-stage usage/cost, projected volume, totals and caveats.
        """
        # 1. Scale the sampled totals up to the full document set (linear extrapolation).
        scale = stats.document_count / stats.sampled_documents if stats.sampled_documents else 1.0
        pages = stats.total_pages * scale
        text_tokens = stats.total_text_tokens * scale
        # Figure count is not a measured signal (unknown until parse): derive it from pages.
        images = pages * assumptions.images_per_page

        # 2. Chunk count drives every text-based stage; overlap re-embeds a fraction of the tokens.
        embed_text_tokens = text_tokens * (1.0 + assumptions.chunk_overlap_ratio)
        chunks = (
            math.ceil(embed_text_tokens / assumptions.target_chunk_tokens) if text_tokens else 0
        )

        # 3. Build each enabled cost-incurring stage's estimate.
        stages: list[StageEstimate] = []
        cls.__add(stages, cls.__embed(plan, embed_text_tokens, chunks, rates))
        cls.__add(stages, cls.__contextualize(plan, chunks, assumptions, rates))
        cls.__add(
            stages,
            cls.__metagen_chunk(plan, chunks, assumptions, rates),
        )
        cls.__add(
            stages,
            cls.__metagen_document(plan, stats.document_count, assumptions, rates),
        )
        cls.__add(stages, cls.__enrich_vlm(plan, images, assumptions, rates))
        cls.__add(stages, cls.__enrich_ocr(plan, pages, assumptions, rates))

        # 4. Roll up totals + volume, and surface the accuracy caveats.
        volume = cls.__volume(plan, int(round(pages)), chunks, assumptions)
        total_cost, cost_complete = cls.__totals(stages)
        return CostEstimate(
            document_count=stats.document_count,
            stages=stages,
            volume=volume,
            total_prompt_tokens=sum(s.prompt_tokens for s in stages),
            total_completion_tokens=sum(s.completion_tokens for s in stages),
            total_cost_usd=total_cost,
            cost_complete=cost_complete,
            assumptions=assumptions,
            caveats=cls.__caveats(plan, stats, assumptions),
        )

    @staticmethod
    def __add(stages: list[StageEstimate], stage: StageEstimate | None) -> None:
        """Append a stage estimate when it is present (a disabled/empty stage yields None)."""
        if stage is not None:
            stages.append(stage)

    @staticmethod
    def __chat_stage(
        stage: str,
        ref: ProviderRef,
        calls: float,
        prompt: float,
        completion: float,
        rates: RateTable,
    ) -> StageEstimate:
        """Shape a chat-priced stage (llm / vlm / structgen), honouring the known/unknown split."""
        cost = rates.chat_cost(ref.model, prompt, completion) if ref.model else None
        return StageEstimate(
            stage=stage,
            family=ref.family,
            provider=ref.kind,
            model=ref.model,
            calls=int(round(calls)),
            prompt_tokens=int(round(prompt)),
            completion_tokens=int(round(completion)),
            cost_usd=cost,
            rate_known=cost is not None,
        )

    @classmethod
    def __embed(
        cls, plan: CostPlan, embed_tokens: float, chunks: int, rates: RateTable
    ) -> StageEstimate | None:
        """The embed stage: tokens over the (overlap-inflated) chunk text; local providers cost 0."""
        ref = plan.embed
        if ref is None:
            return None
        if ref.kind in LOCAL_FREE_KINDS:
            cost: float | None = 0.0
            rate_known = True
        else:
            cost = rates.embed_cost(ref.model, embed_tokens) if ref.model else None
            rate_known = cost is not None
        return StageEstimate(
            stage="embed",
            family="embed",
            provider=ref.kind,
            model=ref.model,
            calls=chunks,
            prompt_tokens=int(round(embed_tokens)),
            completion_tokens=0,
            cost_usd=cost,
            rate_known=rate_known,
        )

    @classmethod
    def __contextualize(
        cls, plan: CostPlan, chunks: int, a: EstimateAssumptions, rates: RateTable
    ) -> StageEstimate | None:
        """The contextualize LLM method: one call per chunk (skipped when no llm method is stacked)."""
        ref = plan.contextualize_llm
        if ref is None or chunks == 0:
            return None
        prompt = chunks * (a.target_chunk_tokens + a.llm_prompt_overhead_tokens)
        completion = chunks * a.llm_output_tokens
        return cls.__chat_stage("contextualize", ref, chunks, prompt, completion, rates)

    @classmethod
    def __metagen_chunk(
        cls, plan: CostPlan, chunks: int, a: EstimateAssumptions, rates: RateTable
    ) -> StageEstimate | None:
        """Chunk-scope metagen: one structured call per chunk (skipped when no chunk fields)."""
        ref = plan.metagen_chunk
        if ref is None or chunks == 0 or plan.n_generated_chunk_fields == 0:
            return None
        prompt = chunks * (a.target_chunk_tokens + a.llm_prompt_overhead_tokens)
        completion = chunks * a.metagen_output_tokens_per_field * plan.n_generated_chunk_fields
        return cls.__chat_stage("metagen_chunk", ref, chunks, prompt, completion, rates)

    @classmethod
    def __metagen_document(
        cls, plan: CostPlan, documents: int, a: EstimateAssumptions, rates: RateTable
    ) -> StageEstimate | None:
        """Document-scope metagen: one structured call per document (skipped when no doc fields)."""
        ref = plan.metagen_document
        if ref is None or documents == 0 or plan.n_generated_document_fields == 0:
            return None
        prompt = documents * (a.metagen_doc_context_tokens + a.llm_prompt_overhead_tokens)
        completion = (
            documents * a.metagen_output_tokens_per_field * plan.n_generated_document_fields
        )
        return cls.__chat_stage("metagen_document", ref, documents, prompt, completion, rates)

    @classmethod
    def __enrich_vlm(
        cls, plan: CostPlan, images: float, a: EstimateAssumptions, rates: RateTable
    ) -> StageEstimate | None:
        """Per-figure VLM captioning: one call per estimated image."""
        ref = plan.enrich_vlm
        if ref is None or images <= 0:
            return None
        prompt = images * a.vlm_prompt_tokens_per_image
        completion = images * a.vlm_output_tokens
        return cls.__chat_stage("enrich_vlm", ref, images, prompt, completion, rates)

    @classmethod
    def __enrich_ocr(
        cls, plan: CostPlan, pages: float, a: EstimateAssumptions, rates: RateTable
    ) -> StageEstimate | None:
        """Paid OCR escalation: priced per (assumed-scanned) page; local rapidocr costs 0."""
        ref = plan.enrich_ocr
        if ref is None:
            return None
        ocr_pages = pages * a.scanned_page_ratio
        if ref.kind in LOCAL_FREE_KINDS:
            cost: float | None = 0.0
            rate_known = True
        else:
            cost = rates.ocr_cost(ref.kind, ocr_pages)
            rate_known = cost is not None
        return StageEstimate(
            stage="enrich_ocr",
            family="ocr",
            provider=ref.kind,
            model=None,
            calls=int(round(ocr_pages)),
            prompt_tokens=0,
            completion_tokens=0,
            pages=int(round(ocr_pages)),
            cost_usd=cost,
            rate_known=rate_known,
        )

    @staticmethod
    def __volume(plan: CostPlan, pages: int, chunks: int, a: EstimateAssumptions) -> VolumeEstimate:
        """Project the material volume: chunks, vectors written and a rough storage footprint."""
        dense = chunks if plan.embed else 0
        sparse = chunks if (plan.embed and plan.embed_sparse) else 0
        text_bytes = int(chunks * a.target_chunk_tokens * a.bytes_per_token)
        vector_bytes = dense * a.embed_dense_dims * 4  # float32 dense vectors
        return VolumeEstimate(
            pages=pages,
            chunks=chunks,
            dense_vectors=dense,
            sparse_vectors=sparse,
            storage_bytes=text_bytes + vector_bytes,
        )

    @staticmethod
    def __totals(stages: list[StageEstimate]) -> tuple[float | None, bool]:
        """Sum priced stages; total is None only when NO stage could be priced, else a lower bound."""
        known = [s.cost_usd for s in stages if s.rate_known and s.cost_usd is not None]
        has_unknown = any(not s.rate_known for s in stages)
        if known:
            return sum(known), not has_unknown
        # No stage carried a known rate: None when that is because a paid stage was unpriceable,
        # else a genuine 0.0 (no cost-incurring stage at all — e.g. a parse-only pipeline).
        return (None if has_unknown else 0.0), not has_unknown

    @staticmethod
    def __caveats(plan: CostPlan, stats: SampleStats, a: EstimateAssumptions) -> list[str]:
        """Human-readable accuracy caveats surfaced so the estimate is never read as an exact quote."""
        caveats = [
            "All figures are ESTIMATES from average token/chunk assumptions, not an exact quote."
        ]
        if stats.sampled_documents and stats.sampled_documents < stats.document_count:
            caveats.append(
                f"Only {stats.sampled_documents} of {stats.document_count} documents were measured; "
                "the rest were scaled linearly."
            )
        estimated_pages = stats.sampled_documents - stats.pages_from_probe
        if estimated_pages > 0:
            caveats.append(
                f"{estimated_pages} of {stats.sampled_documents} sampled documents had no exact "
                "page count; their pages were estimated from file size."
            )
        if plan.enrich_vlm is not None or plan.enrich_ocr is not None:
            caveats.append(
                f"Figures assumed at {a.images_per_page}/page (and {a.scanned_page_ratio:.0%} of "
                "pages needing paid OCR) — the true counts are unknown until parse; this is the "
                "largest source of error for the enrich stage."
            )
        return caveats


__all__ = ["CostEstimator"]

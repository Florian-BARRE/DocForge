# ====== Code Summary ======
# Locks the PURE pre-hoc cost estimator across pipeline shapes: a parse-only pipeline costs ~0, an
# embed-only local pipeline is free-but-voluminous, a paid embed/llm/vlm mix rolls up a real cost,
# and an unknown model prices to a null cost (never a fabricated number) while still reporting tokens.
# Also asserts the CostPlanExtractor reads the canonical default/light PipelineStates correctly.

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest.estimate import (
    CostEstimator,
    CostPlan,
    CostPlanExtractor,
    EstimateAssumptions,
    ProviderRef,
    RateTable,
    SampleStats,
)
from shared_libs.pipelines.ingest.stages.state import default_state, light_state


def _stats(documents: int = 10, pages: float = 100.0, tokens: float = 50000.0) -> SampleStats:
    """A fully-probed sample: 10 documents, 100 pages, 50k body-text tokens."""
    return SampleStats(
        document_count=documents,
        sampled_documents=documents,
        total_pages=pages,
        total_text_tokens=tokens,
        pages_from_probe=documents,
    )


def _assumptions(**overrides) -> EstimateAssumptions:
    """Deterministic assumptions (no figures/OCR unless a test opts in)."""
    base = {"target_chunk_tokens": 500, "images_per_page": 0.0, "scanned_page_ratio": 0.0}
    base.update(overrides)
    return EstimateAssumptions(**base)


def _empty_plan(**overrides) -> CostPlan:
    """A plan with every cost-incurring stage off; tests turn on only what they exercise."""
    base = dict(
        embed=None,
        embed_sparse=False,
        contextualize_llm=None,
        metagen_chunk=None,
        metagen_document=None,
        n_generated_chunk_fields=0,
        n_generated_document_fields=0,
        enrich_vlm=None,
        enrich_ocr=None,
    )
    base.update(overrides)
    return CostPlan(**base)


class TestParseOnly:
    """A pipeline with no cost-incurring stage projects zero cost, completely."""

    def test_parse_only_is_zero_and_complete(self) -> None:
        est = CostEstimator.estimate(_empty_plan(), _stats(), RateTable.default(), _assumptions())
        assert est.stages == []
        assert est.total_cost_usd == 0.0
        assert est.cost_complete is True
        assert est.volume.chunks > 0  # chunking still produces volume
        assert est.volume.dense_vectors == 0
        assert est.total_prompt_tokens == 0


class TestEmbed:
    """The embed stage: local is free, a paid known model has a real cost, unknown is null."""

    def test_local_embed_is_free_but_produces_vectors(self) -> None:
        plan = _empty_plan(embed=ProviderRef("embed", "bge_server", None), embed_sparse=True)
        est = CostEstimator.estimate(plan, _stats(), RateTable.default(), _assumptions())
        embed = next(s for s in est.stages if s.stage == "embed")
        assert embed.cost_usd == 0.0
        assert embed.rate_known is True
        assert est.cost_complete is True
        assert est.volume.dense_vectors == est.volume.chunks
        assert est.volume.sparse_vectors == est.volume.chunks

    def test_paid_known_embed_has_positive_cost(self) -> None:
        plan = _empty_plan(
            embed=ProviderRef("embed", "openai_compatible", "text-embedding-3-small")
        )
        est = CostEstimator.estimate(plan, _stats(), RateTable.default(), _assumptions())
        embed = next(s for s in est.stages if s.stage == "embed")
        assert embed.rate_known is True
        assert embed.cost_usd is not None and embed.cost_usd > 0.0
        assert est.total_cost_usd == pytest.approx(embed.cost_usd)

    def test_unknown_embed_model_prices_to_null(self) -> None:
        plan = _empty_plan(embed=ProviderRef("embed", "openai_compatible", "mystery-embedder"))
        est = CostEstimator.estimate(plan, _stats(), RateTable.default(), _assumptions())
        embed = next(s for s in est.stages if s.stage == "embed")
        assert embed.rate_known is False
        assert embed.cost_usd is None
        assert embed.prompt_tokens > 0  # usage still reported
        assert est.total_cost_usd is None  # the only stage, unpriceable
        assert est.cost_complete is False


class TestFullMix:
    """A paid embed + contextualize LLM + document metagen + figure VLM mix rolls up."""

    def test_all_stages_present_and_summed(self) -> None:
        plan = _empty_plan(
            embed=ProviderRef("embed", "openai_compatible", "text-embedding-3-small"),
            embed_sparse=False,
            contextualize_llm=ProviderRef("llm", "openai_compatible", "gpt-4o-mini"),
            metagen_document=ProviderRef("structgen", "openai_compatible", "gpt-4o-mini"),
            n_generated_document_fields=3,
            enrich_vlm=ProviderRef("vlm", "openai_compatible", "gpt-4o"),
        )
        est = CostEstimator.estimate(
            plan, _stats(), RateTable.default(), _assumptions(images_per_page=0.5)
        )
        kinds = {s.stage for s in est.stages}
        assert kinds == {"embed", "contextualize", "metagen_document", "enrich_vlm"}
        assert est.cost_complete is True
        priced = sum(s.cost_usd for s in est.stages)
        assert est.total_cost_usd == pytest.approx(priced)
        # The VLM stage fired once per estimated image (pages * images_per_page = 100 * 0.5).
        vlm = next(s for s in est.stages if s.stage == "enrich_vlm")
        assert vlm.calls == 50

    def test_mixed_known_and_unknown_is_incomplete_lower_bound(self) -> None:
        plan = _empty_plan(
            embed=ProviderRef("embed", "openai_compatible", "text-embedding-3-small"),
            contextualize_llm=ProviderRef("llm", "openai_compatible", "unlisted-model"),
        )
        est = CostEstimator.estimate(plan, _stats(), RateTable.default(), _assumptions())
        assert est.cost_complete is False
        embed = next(s for s in est.stages if s.stage == "embed")
        assert est.total_cost_usd == pytest.approx(embed.cost_usd)  # unknown excluded from total


class TestMetagenSkips:
    """Metagen with zero generated fields contributes nothing (nothing to generate)."""

    def test_metagen_with_no_fields_is_skipped(self) -> None:
        plan = _empty_plan(
            metagen_chunk=ProviderRef("structgen", "openai_compatible", "gpt-4o-mini"),
            n_generated_chunk_fields=0,
        )
        est = CostEstimator.estimate(plan, _stats(), RateTable.default(), _assumptions())
        assert all(s.stage != "metagen_chunk" for s in est.stages)


class TestScaling:
    """A partial sample is scaled linearly to the full document count, with a caveat."""

    def test_sample_scales_and_flags_caveat(self) -> None:
        stats = SampleStats(
            document_count=100,
            sampled_documents=10,
            total_pages=100.0,
            total_text_tokens=50000.0,
            pages_from_probe=10,
        )
        plan = _empty_plan(
            embed=ProviderRef("embed", "openai_compatible", "text-embedding-3-small")
        )
        est = CostEstimator.estimate(plan, stats, RateTable.default(), _assumptions())
        # 10x the sample ⇒ ~10x the chunks/tokens of the fully-probed 10-doc case.
        full = CostEstimator.estimate(plan, _stats(), RateTable.default(), _assumptions())
        assert est.volume.chunks == pytest.approx(full.volume.chunks * 10, rel=0.01)
        assert any("scaled linearly" in c for c in est.caveats)


class TestPlanExtraction:
    """The extractor reads the canonical PipelineStates the studio ships."""

    def test_default_state_embeds_locally_no_paid_stages(self) -> None:
        plan = CostPlanExtractor.extract(default_state(), 0, 0)
        assert plan.embed is not None and plan.embed.kind == "bge_server"
        assert plan.contextualize_llm is None  # doc_meta + breadcrumb, no llm method
        assert plan.metagen_chunk is None and plan.metagen_document is None  # off by default
        assert plan.enrich_vlm is None and plan.enrich_ocr is None  # enrich off by default

    def test_light_state_is_embed_only(self) -> None:
        plan = CostPlanExtractor.extract(light_state(), 0, 0)
        assert plan.embed is not None
        assert plan.contextualize_llm is None
        assert plan.metagen_chunk is None and plan.metagen_document is None

    def test_extractor_reads_enabled_paid_providers(self) -> None:
        state = default_state()
        state.enrich_on = True
        state.metadoc_on = True
        plan = CostPlanExtractor.extract(state, 0, 2)
        assert plan.enrich_vlm is not None and plan.enrich_vlm.family == "vlm"
        # The OCR chain escalates rapidocr → mistral: the paid step is the one that must be costed.
        assert plan.enrich_ocr is not None and plan.enrich_ocr.kind == "mistral"
        assert plan.metagen_document is not None

    def test_paddle_head_is_free_so_the_paid_ocr_escalation_is_costed(self) -> None:
        """A [paddle → mistral] OCR chain must cost the MISTRAL step: paddle is a LOCAL (free) kind.
        A hardcoded local list in plan.py omitted paddle, so it was treated as the paid step and the
        real Mistral escalation was priced at $0.00 — the canonical LOCAL_FREE_KINDS fixes it."""
        state = default_state()
        state.enrich_on = True
        ocr = next(spec for spec in state.chains.values() if spec.family == "ocr")
        ocr.steps[0].kind = "paddle"  # swap the local head rapidocr → paddle

        plan = CostPlanExtractor.extract(state, 0, 0)

        assert plan.enrich_ocr is not None
        assert plan.enrich_ocr.kind == "mistral"  # NOT paddle (which would price $0)

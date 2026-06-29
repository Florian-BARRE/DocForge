# ====== Code Summary ======
# Tests for the two native stages migrated in P1b increment 3 — enrich (S2) and embed_index (S6).
# Enrich is now decomposed into REAL per-capability steps (classify -> ocr -> vlm -> chart): the tests
# assert the forced ClassVars, the conditional step set, the legacy S2 fingerprint params (delegated
# to the EnrichResources bundle), the per-figure routing reproduced across the per-capability passes
# (classify records the decision; ocr/vlm only touch routed figures; chart is conditional), the
# provider-call cache hit/miss counters, and an end-to-end mixed-figure run matching the legacy
# enriched-IR shape. embed_index keeps its 2-real-step assertions. build_pipeline still yields the
# canonical 7-key order. Everything is mocked — no live stack.

# ====== Standard Library Imports ======
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from common_libs.config.pipeline import build_default_pipeline
from common_libs.domain.ir.models import (
    Block,
    BlockType,
    DocumentIR,
    FigureEnrichment,
    FigureKind,
    Provenance,
)
from common_libs.providers.classifier.base import ClassificationResult
from common_libs.providers.results.ocr_result import OcrResult
from common_libs.providers.results.vlm_result import VlmResult
from common_libs.pipeline.assembly import ProviderRegistry
from common_libs.pipeline.assembly.stage_assembler import build_pipeline
from common_libs.pipeline.base import CachePolicy, ErrorPolicy
from common_libs.pipeline.bricks.chain import Chain
from common_libs.pipeline.bricks.chain.gate import ChainGate, ChainGateConfig
from common_libs.pipeline.ingest.stages.embed_index import EmbedIndexStage, EmbedStep, IndexStep
from common_libs.pipeline.ingest.stages.embed_index.steps.embed_step import EMBED_ARTIFACTS_KEY
from common_libs.pipeline.ingest.stages.enrich import (
    ChartStep,
    ClassifyStep,
    EnrichResources,
    EnrichResult,
    EnrichStage,
    OcrStep,
    VlmStep,
)
from common_libs.pipeline.ingest.stages.enrich.scratch import ENRICH_SCRATCH_KEY, EnrichScratch, FigureWork
from common_libs.pipeline.stages.context import PipelineContext, StageDeps
from common_libs.pipeline.stages.s6_embed_index.core import S6EmbedIndexStage

_CANONICAL_ORDER = ["ingest", "parse", "enrich", "chunk", "contextualize", "metagen", "embed_index"]


# ─── Test doubles (real chains + fake providers + a dict-backed provider cache) ──────────────────


class _FakeClassifier:
    """Classifier double — returns a kind looked up by the crop bytes the test seeded."""

    name = "fake_cls"
    version = "1"

    def __init__(self, kind_by_bytes: dict[bytes, FigureKind]) -> None:
        self._kinds = kind_by_bytes

    async def classify(self, img_bytes: bytes, label_hint: str | None = None) -> ClassificationResult:
        _ = label_hint
        return ClassificationResult(kind=self._kinds[img_bytes], confidence=0.9)


class _FakeOcr:
    """OCR double — always returns a fixed high-confidence text."""

    name = "fake_ocr"
    version = "1"

    async def extract(self, img_bytes: bytes, hint: Any) -> OcrResult:
        _ = (img_bytes, hint)
        return OcrResult(text="OCR-TEXT", confidence=0.9)


class _FakeVlm:
    """VLM double — returns a description + a structured chart table (schema is ignored)."""

    name = "fake_vlm"
    version = "1"

    async def describe(self, img_bytes: bytes, grounding: str | None = None, schema: Any = None) -> VlmResult:
        _ = (img_bytes, grounding, schema)
        return VlmResult(description="DESC", structured={"table": [["Q1", "10"]]}, quality=1.0)


class _DictCache:
    """Provider-call cache double — a plain dict so duplicate crops register as cache hits."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, call_fp: str) -> str | None:
        return self.store.get(call_fp)

    async def put(self, *, call_fp: str, capability: str, provider_id: str,
                  provider_version: str, content_hash: str, result_json: str) -> None:
        _ = (capability, provider_id, provider_version, content_hash)
        self.store[call_fp] = result_json


class _FakeS3:
    """Object-store double — the crop bytes are the crop key encoded (distinct per figure)."""

    async def download(self, crop_key: str) -> bytes:
        return crop_key.encode("utf-8")


def _permissive(stage: str, provider: object) -> Chain[Any, Any]:
    """A single-provider chain with a permissive gate (accepts any score)."""
    return Chain(stage=stage, providers=[provider], gate=ChainGate(ChainGateConfig(min_score=0.0)))


def _figure_block(idx: int, crop_key: str) -> Block:
    """A FIGURE block carrying a placeholder enrichment (the classify step overwrites it)."""
    return Block(
        id=f"b{idx}",
        type=BlockType.FIGURE,
        prov=Provenance(page=0, bbox=(0.0, 0.0, 1.0, 1.0)),
        reading_order=idx,
        figure=FigureEnrichment(kind=FigureKind.PHOTO, crop_key=crop_key, relevance=0.0),
    )


def _ir(crop_keys: list[str]) -> DocumentIR:
    """Build a one-page IR whose blocks are FIGUREs at the given crop keys."""
    blocks = [_figure_block(i, key) for i, key in enumerate(crop_keys)]
    return DocumentIR(doc_id="d1", source_hash="h", n_pages=1, language="en", blocks=blocks)


def _chain(*provider_names: str) -> MagicMock:
    """A mock chain whose .providers expose a .name (what ChainHelpers.default_provider_id reads)."""
    chain = MagicMock()
    chain.providers = [SimpleNamespace(name=n) for n in provider_names]
    return chain


def _resources(*, kinds: dict[bytes, FigureKind], ocr: bool, vlm: bool, chart: bool) -> EnrichResources:
    """Assemble an EnrichResources with real chains + the dict cache + fake object store."""
    return EnrichResources(
        classifier_chain=_permissive("classifier", _FakeClassifier(kinds)),
        ocr_chain=_permissive("ocr", _FakeOcr()) if ocr else None,
        vlm_chain=_permissive("vlm", _FakeVlm()) if vlm else None,
        s3=_FakeS3(),
        provider_cache=_DictCache(),
        chart_to_data=chart,
    )


def _work(block_id: str, crop_key: str, kind: FigureKind, *, do_ocr: bool = False,
          do_vlm: bool = False) -> FigureWork:
    """A FigureWork already past the classify stage (crop downloaded, kind + routing set)."""
    return FigureWork(
        block_id=block_id,
        crop_key=crop_key,
        crop_bytes=crop_key.encode("utf-8"),
        crop_hash=crop_key,  # any stable string works as the cache content key in tests
        kind=kind,
        relevance=0.9,
        decorative=(kind == FigureKind.DECORATIVE),
        do_ocr=do_ocr,
        do_vlm=do_vlm,
        use_chart_schema=False,
    )


def _ctx_with_scratch(figures: dict[str, FigureWork]) -> PipelineContext:
    """Build a context whose IR + scratch carry the given figure work items (ids aligned)."""
    ir = _ir([w.crop_key for w in figures.values()])
    for block, work in zip(ir.blocks, figures.values()):
        object.__setattr__(block, "id", work.block_id)
    ctx = PipelineContext(ir=ir)
    scratch = EnrichScratch(language="en")
    scratch.figures = figures
    ctx.aux[ENRICH_SCRATCH_KEY] = scratch
    return ctx


# ─── enrich (S2) — native stage contract ─────────────────────────────────────────────────────────


class TestEnrichStageContract:
    """The native EnrichStage declares the s2 contract and builds its steps conditionally."""

    def test_classvars(self) -> None:
        assert EnrichStage.SPEC.key == "enrich"
        assert EnrichStage.SPEC.after == ("parse",)
        assert EnrichStage.SPEC.consumes == ("parse_result", "ir")
        assert EnrichStage.SPEC.produces == ("enrich_result", "ir")
        assert EnrichStage.SPEC.cache_policy == CachePolicy.NODE_CACHED
        assert EnrichStage.SPEC.error_policy == ErrorPolicy.FAIL_DOC
        assert EnrichStage.SPEC.code_version == "1.0"

    def test_all_steps_built_when_all_chains_and_chart(self) -> None:
        stage = EnrichStage(_resources(kinds={}, ocr=True, vlm=True, chart=True))
        assert [type(s) for s in stage.steps] == [ClassifyStep, OcrStep, VlmStep, ChartStep]

    def test_only_classify_when_no_optional_capabilities(self) -> None:
        stage = EnrichStage(_resources(kinds={}, ocr=False, vlm=False, chart=False))
        assert [type(s) for s in stage.steps] == [ClassifyStep]

    def test_fingerprint_params_delegates_to_resources(self) -> None:
        resources = _resources(kinds={}, ocr=True, vlm=False, chart=True)
        assert EnrichStage(resources).fingerprint_params() == resources.params_for_fingerprint()

    def test_resources_fingerprint_shape(self) -> None:
        # The legacy S2 node fingerprint shape (chain signatures + chart flag, "none" when absent).
        params = _resources(kinds={}, ocr=False, vlm=False, chart=False).params_for_fingerprint()
        assert set(params) == {"classifier_chain", "ocr_chain", "vlm_chain", "chart_to_data"}
        assert params["ocr_chain"] == "none"
        assert params["vlm_chain"] == "none"
        assert params["chart_to_data"] is False

    def test_describe_models_real_steps(self) -> None:
        stage = EnrichStage(EnrichResources(
            classifier_chain=_chain("vit"),
            ocr_chain=_chain("paddle"),
            vlm_chain=_chain("qwen"),
            s3=MagicMock(),
            provider_cache=MagicMock(),
            chart_to_data=True,
        ))
        schema = stage.describe()
        assert [s.key for s in schema.steps] == ["classify", "ocr", "vlm", "chart"]
        assert schema.steps[0].kind == "chain"
        assert schema.steps[0].category == "classify"
        assert schema.steps[0].providers == ["vit"]
        assert schema.steps[3].kind == "step"  # chart-to-data is a plain post-processing step

    def test_describe_omits_disabled_routes(self) -> None:
        stage = EnrichStage(EnrichResources(
            classifier_chain=_chain("vit"), ocr_chain=None, vlm_chain=None,
            s3=MagicMock(), provider_cache=MagicMock(), chart_to_data=False,
        ))
        assert [s.key for s in stage.describe().steps] == ["classify"]


# ─── enrich (S2) — per-step behaviour + end-to-end parity ─────────────────────────────────────────


class TestEnrichSteps:
    """Each capability step touches exactly the figures the routing marked; counters are preserved."""

    @pytest.mark.asyncio
    async def test_classify_records_routing_and_counters(self) -> None:
        crops = ["crop/0", "crop/1", "crop/2"]
        kinds = {
            b"crop/0": FigureKind.DECORATIVE,
            b"crop/1": FigureKind.CHART,
            b"crop/2": FigureKind.PHOTO,
        }
        resources = _resources(kinds=kinds, ocr=True, vlm=True, chart=True)
        ctx = PipelineContext(ir=_ir(crops))
        step = ClassifyStep(
            classifier_chain=resources.classifier_chain, s3=resources.s3,
            provider_cache=resources.provider_cache, ocr_enabled=True, vlm_enabled=True,
            chart_to_data=True,
        )

        await step.run(ctx)

        scratch = ctx.aux[ENRICH_SCRATCH_KEY]
        # The routing decision was recorded once, per figure, reproducing the legacy table.
        assert scratch.figures["b0"].decorative is True
        assert (scratch.figures["b1"].do_ocr, scratch.figures["b1"].do_vlm) == (True, True)
        assert scratch.figures["b1"].use_chart_schema is True       # CHART + chart_to_data
        assert (scratch.figures["b2"].do_ocr, scratch.figures["b2"].do_vlm) == (False, True)  # PHOTO
        # Every figure was classified (a fresh-crop miss) and counted as processed.
        assert scratch.counters.figures_processed == 3
        assert scratch.counters.classifier_calls == 3
        assert scratch.counters.classifier_cache_hits == 0

    @pytest.mark.asyncio
    async def test_classify_dedups_identical_crops(self) -> None:
        # Two figures with the SAME crop bytes → the second classify is a provider-call cache HIT.
        crops = ["crop/dup", "crop/dup"]
        resources = _resources(kinds={b"crop/dup": FigureKind.PHOTO}, ocr=False, vlm=True, chart=False)
        ctx = PipelineContext(ir=_ir(crops))
        step = ClassifyStep(
            classifier_chain=resources.classifier_chain, s3=resources.s3,
            provider_cache=resources.provider_cache, ocr_enabled=False, vlm_enabled=True,
            chart_to_data=False,
        )

        await step.run(ctx)

        scratch = ctx.aux[ENRICH_SCRATCH_KEY]
        assert scratch.counters.classifier_calls == 1
        assert scratch.counters.classifier_cache_hits == 1

    @pytest.mark.asyncio
    async def test_ocr_step_only_touches_routed_figures(self) -> None:
        ctx = _ctx_with_scratch({
            "b0": _work("b0", "crop/0", FigureKind.SCANNED_TEXT, do_ocr=True),
            "b1": _work("b1", "crop/1", FigureKind.PHOTO, do_ocr=False),
        })
        await OcrStep(_permissive("ocr", _FakeOcr()), _DictCache()).run(ctx)

        scratch = ctx.aux[ENRICH_SCRATCH_KEY]
        assert scratch.figures["b0"].ocr_text == "OCR-TEXT"
        assert scratch.figures["b0"].ocr_trace is not None
        assert scratch.figures["b1"].ocr_text is None        # not routed for OCR
        assert scratch.figures["b1"].ocr_trace is None
        assert scratch.counters.ocr_calls == 1

    @pytest.mark.asyncio
    async def test_vlm_step_only_touches_routed_figures(self) -> None:
        ctx = _ctx_with_scratch({
            "b0": _work("b0", "crop/0", FigureKind.PHOTO, do_vlm=True),
            "b1": _work("b1", "crop/1", FigureKind.SCANNED_TEXT, do_vlm=False),
        })
        await VlmStep(_permissive("vlm", _FakeVlm()), _DictCache()).run(ctx)

        scratch = ctx.aux[ENRICH_SCRATCH_KEY]
        assert scratch.figures["b0"].description == "DESC"
        assert scratch.figures["b0"].vlm_structured == {"table": [["Q1", "10"]]}
        assert scratch.figures["b1"].description is None     # not routed for VLM
        assert scratch.counters.vlm_calls == 1

    @pytest.mark.asyncio
    async def test_chart_step_extracts_table_only_for_chart_schema(self) -> None:
        chart_work = _work("b0", "crop/0", FigureKind.CHART, do_vlm=True)
        chart_work.use_chart_schema = True
        chart_work.vlm_structured = {"table": [["Q1", "10"], ["Q2", "20"]]}
        plain_work = _work("b1", "crop/1", FigureKind.DIAGRAM, do_vlm=True)
        plain_work.use_chart_schema = False
        plain_work.vlm_structured = {"table": [["x"]]}
        ctx = _ctx_with_scratch({"b0": chart_work, "b1": plain_work})

        await ChartStep().run(ctx)

        scratch = ctx.aux[ENRICH_SCRATCH_KEY]
        assert scratch.figures["b0"].data_table == [["Q1", "10"], ["Q2", "20"]]
        assert scratch.figures["b1"].data_table is None      # no chart schema → no extraction
        assert scratch.counters.chart_extractions == 1

    @pytest.mark.asyncio
    async def test_end_to_end_mixed_figures_matches_legacy_shape(self) -> None:
        crops = ["crop/0", "crop/1", "crop/2", "crop/3", "crop/4"]
        kinds = {
            b"crop/0": FigureKind.DECORATIVE,
            b"crop/1": FigureKind.SCANNED_TEXT,
            b"crop/2": FigureKind.CHART,
            b"crop/3": FigureKind.DIAGRAM,
            b"crop/4": FigureKind.PHOTO,
        }
        stage = EnrichStage(_resources(kinds=kinds, ocr=True, vlm=True, chart=True))
        ctx = PipelineContext(parse_result=object(), ir=_ir(crops))

        await stage.run(ctx)

        result = ctx.enrich_result
        assert isinstance(result, EnrichResult)
        figs = {b.id: b.figure for b in ctx.ir.blocks}
        # DECORATIVE: skipped — kind only, no enrichment payload.
        assert figs["b0"].kind == FigureKind.DECORATIVE
        assert (figs["b0"].ocr_text, figs["b0"].description, figs["b0"].data_table) == (None, None, None)
        # SCANNED_TEXT: OCR only (not in the VLM kinds).
        assert (figs["b1"].ocr_text, figs["b1"].description) == ("OCR-TEXT", None)
        # CHART: OCR + VLM + chart-to-data.
        assert figs["b2"].ocr_text == "OCR-TEXT"
        assert figs["b2"].description == "DESC"
        assert figs["b2"].data_table == [["Q1", "10"]]
        # DIAGRAM: OCR + VLM, but no chart table (not a CHART).
        assert (figs["b3"].ocr_text, figs["b3"].description, figs["b3"].data_table) == ("OCR-TEXT", "DESC", None)
        # PHOTO: VLM only.
        assert (figs["b4"].ocr_text, figs["b4"].description) == (None, "DESC")
        # Counters reproduce the legacy per-figure accounting.
        assert result.figures_processed == 5
        assert result.classifier_calls == 5
        assert result.ocr_calls == 3      # SCANNED_TEXT + CHART + DIAGRAM
        assert result.vlm_calls == 3      # CHART + DIAGRAM + PHOTO
        assert result.chart_extractions == 1


# ─── embed_index (S6) ──────────────────────────────────────────────────────────────────────────


class TestEmbedIndexStage:
    """The native EmbedIndexStage matches the deleted s6 adapter contract; 2 REAL steps (embed/index)."""

    def test_classvars(self) -> None:
        assert EmbedIndexStage.SPEC.key == "embed_index"
        assert EmbedIndexStage.SPEC.after == ("metagen",)
        assert EmbedIndexStage.SPEC.consumes == ("chunks", "collection_id", "metadata_fields", "doc_meta")
        assert EmbedIndexStage.SPEC.produces == ("embed_result",)
        assert EmbedIndexStage.SPEC.cache_policy == CachePolicy.IDEMPOTENT_WRITE
        assert EmbedIndexStage.SPEC.error_policy == ErrorPolicy.FAIL_DOC

    def test_two_real_steps(self) -> None:
        steps = EmbedIndexStage(MagicMock()).steps
        assert [type(s) for s in steps] == [EmbedStep, IndexStep]

    @pytest.mark.asyncio
    async def test_embed_step_runs_chain_and_stashes_artifacts(self) -> None:
        artifacts = SimpleNamespace(tag="ARTIFACTS")
        inner = MagicMock()
        inner.embed = AsyncMock(return_value=artifacts)
        ctx = PipelineContext(chunks=["c0"], metadata_fields=[], doc_meta={"k": "v"})

        await EmbedStep(inner).run(ctx)

        inner.embed.assert_awaited_once_with(["c0"], [], {"k": "v"})
        assert ctx.aux[EMBED_ARTIFACTS_KEY] is artifacts

    @pytest.mark.asyncio
    async def test_index_step_opens_local_session_and_delegates(
        self, mock_postgres: MagicMock, mock_session: AsyncMock
    ) -> None:
        artifacts = SimpleNamespace(tag="ARTIFACTS")
        result = SimpleNamespace(n_embedded=1)
        inner = MagicMock()
        inner.index = AsyncMock(return_value=result)
        ctx = PipelineContext(
            chunks=["c0"],
            collection_id="col",
            metadata_fields=[],
            doc_meta={"k": "v"},
            deps=StageDeps(postgres=mock_postgres),
        )
        ctx.aux[EMBED_ARTIFACTS_KEY] = artifacts

        await IndexStep(inner).run(ctx)

        inner.index.assert_awaited_once_with(
            artifacts,
            chunks=["c0"],
            collection_name="col",
            session=mock_session,
            metadata_fields=[],
            doc_meta={"k": "v"},
        )
        assert ctx.embed_result is result

    @pytest.mark.asyncio
    async def test_stage_run_threads_embed_to_index_via_ctx(
        self, mock_postgres: MagicMock, mock_session: AsyncMock
    ) -> None:
        artifacts = SimpleNamespace(tag="ARTIFACTS")
        result = SimpleNamespace(n_embedded=1)
        inner = MagicMock()
        inner.embed = AsyncMock(return_value=artifacts)
        inner.index = AsyncMock(return_value=result)
        ctx = PipelineContext(
            chunks=["c0"], collection_id="col", metadata_fields=[], doc_meta={"k": "v"},
            deps=StageDeps(postgres=mock_postgres),
        )

        await EmbedIndexStage(inner).run(ctx)

        inner.embed.assert_awaited_once_with(["c0"], [], {"k": "v"})
        assert inner.index.await_args.args[0] is artifacts
        assert ctx.embed_result is result

    def test_describe_models_embed_and_index_steps(self) -> None:
        inner = MagicMock()
        inner.embed_chain = _chain("bge_m3")
        schema = EmbedIndexStage(inner).describe()
        assert [s.key for s in schema.steps] == ["embed", "index"]
        assert schema.steps[0].kind == "chain"
        assert schema.steps[0].category == "embed"
        assert schema.steps[0].providers == ["bge_m3"]
        assert schema.steps[1].kind == "step"


# ─── build_pipeline parity (both stages native, order + inner signatures unchanged) ──


class TestBuildPipelineParity:
    """build_pipeline yields the canonical order; enrich carries an EnrichResources bundle."""

    def _build(self) -> dict:
        registry = ProviderRegistry(s3=MagicMock(), provider_cache=MagicMock(), runtime_config=RUNTIME_CONFIG)
        dp = build_default_pipeline(RUNTIME_CONFIG)
        deps = StageDeps(s3=MagicMock(), postgres=MagicMock(), chunk_repo=MagicMock())
        stages = build_pipeline(dp, registry, deps, qdrant=MagicMock())
        return {"registry": registry, "dp": dp, "stages": stages, "by_key": {s.SPEC.key: s for s in stages}}

    def test_order_and_native_types(self) -> None:
        ctx = self._build()
        assert [s.SPEC.key for s in ctx["stages"]] == _CANONICAL_ORDER
        assert isinstance(ctx["by_key"]["enrich"], EnrichStage)
        assert isinstance(ctx["by_key"]["enrich"]._resources, EnrichResources)
        assert isinstance(ctx["by_key"]["embed_index"], EmbedIndexStage)
        assert isinstance(ctx["by_key"]["embed_index"]._inner, S6EmbedIndexStage)

    def test_inner_signatures_match_builders(self) -> None:
        ctx = self._build()
        registry, dp, by_key = ctx["registry"], ctx["dp"], ctx["by_key"]
        # enrich fingerprint params identical to invoking the shared S2 builder directly.
        assert (
            by_key["enrich"]._resources.params_for_fingerprint()
            == registry._build_s2(dp.enrich).params_for_fingerprint()
        )
        # embed chain signature identical to invoking the shared embed builder directly.
        assert (
            by_key["embed_index"]._inner.embed_chain.signature()
            == registry._build_embed_chain(
                dp.embed.chain, dp.embed.gate, getattr(dp.embed, "sparse", None)
            ).signature()
        )

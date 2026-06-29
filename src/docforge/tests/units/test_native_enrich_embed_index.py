# ====== Code Summary ======
# Parity tests for the two native stages migrated in P1b increment 3 — enrich (S2) and embed_index
# (S6) — which replaced the last two adapters. They assert byte-for-byte contract parity with the
# deleted adapters: identical forced ClassVars (KEY/AFTER/IO/cache/error, + NODE_TYPE for the
# node-cached enrich), the S2 fingerprint params (delegated to the inner stage), the same ctx
# round-trips (enrich: delegate s2.run; embed_index: open a LOCAL session + delegate s6.run), and
# the conceptual sub-step modeling in describe() (enrich = 4 steps conditional on chains/chart;
# embed_index = 2 steps). build_pipeline still yields the canonical 7-key order with both native.
# Everything is mocked — no live stack.

# ====== Standard Library Imports ======
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from common_libs.config.pipeline import build_default_pipeline
from common_libs.pipeline.assembly import ProviderRegistry
from common_libs.pipeline.assembly.stage_assembler import build_pipeline
from common_libs.pipeline.base import CachePolicy, ErrorPolicy
from common_libs.pipeline.ingest.stages.embed_index import EmbedIndexStage, EmbedStep, IndexStep
from common_libs.pipeline.ingest.stages.embed_index.steps.embed_step import EMBED_ARTIFACTS_KEY
from common_libs.pipeline.ingest.stages.enrich import EnrichStage, EnrichStep
from common_libs.pipeline.stages.context import PipelineContext, StageDeps
from common_libs.pipeline.stages.s2_enrich.core import S2EnrichStage
from common_libs.pipeline.stages.s6_embed_index.core import S6EmbedIndexStage

_CANONICAL_ORDER = ["ingest", "parse", "enrich", "chunk", "contextualize", "metagen", "embed_index"]


def _chain(*provider_names: str) -> MagicMock:
    """A mock chain whose .providers expose a .name (what ChainHelpers.default_provider_id reads)."""
    chain = MagicMock()
    chain.providers = [SimpleNamespace(name=n) for n in provider_names]
    return chain


# ─── enrich (S2) ─────────────────────────────────────────────────────────────────


class TestEnrichStage:
    """The native EnrichStage matches the deleted s2 adapter contract; describe models 4 steps."""

    def test_classvars(self) -> None:
        assert EnrichStage.SPEC.key == "enrich"
        assert EnrichStage.SPEC.after == ("parse",)
        assert EnrichStage.SPEC.consumes == ("parse_result", "ir")
        assert EnrichStage.SPEC.produces == ("enrich_result", "ir")
        assert EnrichStage.SPEC.cache_policy == CachePolicy.NODE_CACHED
        assert EnrichStage.SPEC.error_policy == ErrorPolicy.FAIL_DOC
        assert EnrichStage.SPEC.key == "enrich"
        assert EnrichStage.SPEC.code_version == "1.0"

    def test_single_executing_step(self) -> None:
        inner = MagicMock()
        stage = EnrichStage(inner)
        assert len(stage.steps) == 1
        assert isinstance(stage.steps[0], EnrichStep)

    def test_fingerprint_params_delegates_to_inner(self) -> None:
        legacy = {"classifier_chain": "vit:1", "ocr_chain": "none", "vlm_chain": "none", "chart_to_data": False}
        inner = MagicMock()
        inner.params_for_fingerprint = MagicMock(return_value=legacy)
        assert EnrichStage(inner).fingerprint_params() == legacy
        assert EnrichStage(inner).key == "enrich"

    @pytest.mark.asyncio
    async def test_run_round_trip(self) -> None:
        s1 = object()
        result = SimpleNamespace(ir="ENRICHED_IR")
        inner = MagicMock()
        inner.run = AsyncMock(return_value=result)
        ctx = PipelineContext(parse_result=s1, ir="RAW_IR")

        await EnrichStage(inner).run(ctx)

        inner.run.assert_awaited_once_with(s1, "RAW_IR")
        assert ctx.enrich_result is result
        assert ctx.ir == "ENRICHED_IR"

    def test_describe_models_four_conceptual_steps(self) -> None:
        inner = MagicMock()
        inner._classifier_chain = _chain("vit")
        inner._ocr_chain = _chain("paddle")
        inner._vlm_chain = _chain("qwen")
        inner._chart_to_data = True

        schema = EnrichStage(inner).describe()
        assert [s.key for s in schema.steps] == ["classify", "ocr", "vlm", "chart"]
        classify = schema.steps[0]
        assert classify.kind == "chain"
        assert classify.category == "classify"
        assert classify.providers == ["vit"]
        assert schema.steps[3].kind == "step"  # chart-to-data is a conditional plain sub-step

    def test_describe_omits_disabled_routes(self) -> None:
        # No OCR/VLM chain + chart disabled → only the (always-present) classify sub-step.
        inner = MagicMock()
        inner._classifier_chain = _chain("vit")
        inner._ocr_chain = None
        inner._vlm_chain = None
        inner._chart_to_data = False

        schema = EnrichStage(inner).describe()
        assert [s.key for s in schema.steps] == ["classify"]


# ─── embed_index (S6) ──────────────────────────────────────────────────────────────


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

        # The embed phase runs the chain over chunks/fields and stashes vectors for the index step.
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

        # Session opened locally (never a ctx key); collection_id mapped to collection_name; the
        # embed artifacts are passed through to the index phase.
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
        # End-to-end through the stage: embed() -> ctx.aux -> index(), byte-identical to s6.run order.
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
    """build_pipeline yields the canonical order; enrich/embed_index are native wrapping the legacy inner."""

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
        assert isinstance(ctx["by_key"]["enrich"]._inner, S2EnrichStage)
        assert isinstance(ctx["by_key"]["embed_index"], EmbedIndexStage)
        assert isinstance(ctx["by_key"]["embed_index"]._inner, S6EmbedIndexStage)

    def test_inner_signatures_match_builders(self) -> None:
        ctx = self._build()
        registry, dp, by_key = ctx["registry"], ctx["dp"], ctx["by_key"]
        # enrich fingerprint params identical to invoking the shared S2 builder directly.
        assert (
            by_key["enrich"]._inner.params_for_fingerprint()
            == registry._build_s2(dp.enrich).params_for_fingerprint()
        )
        # embed chain signature identical to invoking the shared embed builder directly.
        assert (
            by_key["embed_index"]._inner.embed_chain.signature()
            == registry._build_embed_chain(
                dp.embed.chain, dp.embed.gate, getattr(dp.embed, "sparse", None)
            ).signature()
        )

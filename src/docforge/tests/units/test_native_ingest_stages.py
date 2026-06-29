# ====== Code Summary ======
# Parity tests for the four native ingest stages migrated in P1b increment 2 (ingest/chunk/
# contextualize/metagen), each replacing the adapter of the same name. They assert byte-for-byte
# contract parity with the adapters they replaced: identical forced ClassVars (KEY/AFTER/IO/cache/
# error, plus NODE_TYPE/NODE_VERSION for the node-cached ingest stage), the same ctx round-trip
# (read CONSUMES -> delegate -> write PRODUCES), the S0 fingerprint_params (converter name/version),
# and the metagen doc_meta merge precedence (implicit < generated < user). build_pipeline still
# yields the canonical 7-stage topo order with these stages now NATIVE. Everything is mocked.

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
from common_libs.pipeline.ingest.stages.chunk import ChunkStage, ChunkStep
from common_libs.pipeline.ingest.stages.contextualize import ContextualizeStage, ContextualizeStep
from common_libs.pipeline.ingest.stages.ingest import IngestDocStage, IngestDocStep
from common_libs.pipeline.ingest.stages.metagen import MetagenStage, MetagenStep
from common_libs.pipeline.stages.context import PipelineContext, StageDeps
from common_libs.pipeline.stages.s0_ingest.core import S0IngestStage
from common_libs.pipeline.stages.s4_chunk.core import S4ChunkStage
from common_libs.pipeline.stages.s5_contextualize.core import S5ContextualizeStage
from common_libs.pipeline.stages.s5b_metagen.core import S5bMetagenStage

_CANONICAL_ORDER = ["ingest", "parse", "enrich", "chunk", "contextualize", "metagen", "embed_index"]


def _inner(return_value: object) -> MagicMock:
    """Build a mock legacy stage whose async run() returns ``return_value``."""
    stage = MagicMock()
    stage.run = AsyncMock(return_value=return_value)
    return stage


def _fake_ir(language: str = "en") -> SimpleNamespace:
    """A minimal IR stand-in exposing the system fields the metagen stage reads for doc_meta."""
    return SimpleNamespace(
        language=language, n_pages=3, blocks=["b0", "b1"], figure_blocks=["f0"], table_blocks=[]
    )


# ─── ClassVar matrix: native stages declare the same contract as the adapters they replaced ───


class TestNativeStageClassVars:
    """Each native stage pins today's ordering, IO, cache policy, and error policy."""

    _CASES = [
        (IngestDocStage, "ingest", CachePolicy.NODE_CACHED, (), ("original_bytes", "filename", "doc_id"), ("ingest_result", "source_hash")),
        (ChunkStage, "chunk", CachePolicy.IDEMPOTENT_WRITE, ("enrich",), ("ir",), ("chunk_result", "chunks")),
        (ContextualizeStage, "contextualize", CachePolicy.IDEMPOTENT_WRITE, ("chunk",), ("chunks", "ir"), ("contextualize_result", "chunks")),
        (MetagenStage, "metagen", CachePolicy.IDEMPOTENT_WRITE, ("contextualize",), ("chunks", "ir", "ingest_result", "doc_user_meta"), ("metagen_result", "chunks", "doc_fields", "doc_meta")),
    ]

    @pytest.mark.parametrize("cls,key,cache,after,consumes,produces", _CASES)
    def test_classvars(self, cls, key, cache, after, consumes, produces) -> None:
        assert cls.SPEC.key == key
        assert cls.SPEC.cache_policy == cache
        assert cls.SPEC.after == after
        assert cls.SPEC.consumes == consumes
        assert cls.SPEC.produces == produces
        assert cls.SPEC.error_policy == ErrorPolicy.FAIL_DOC
        assert cls.CONFIG is None

    def test_ingest_node_identity_pins_legacy_s0(self) -> None:
        # The node cache keys on the StageKey (ingest) + code_version "1.0".
        assert IngestDocStage.SPEC.key == "ingest"
        assert IngestDocStage.SPEC.code_version == "1.0"
        converter = SimpleNamespace(name="gotenberg", version="8")
        assert IngestDocStage(SimpleNamespace(_converter=converter)).key == "ingest"


class TestIngestStage:
    """ingest stage: ctx round-trip + the S0 fingerprint params (converter name/version)."""

    def test_single_native_step(self) -> None:
        assert isinstance(IngestDocStage(SimpleNamespace(_converter=None)).steps[0], IngestDocStep)

    def test_fingerprint_params_surfaces_converter(self) -> None:
        inner = SimpleNamespace(_converter=SimpleNamespace(name="gotenberg", version="8"))
        assert IngestDocStage(inner).fingerprint_params() == {
            "converter_name": "gotenberg",
            "converter_version": "8",
        }

    @pytest.mark.asyncio
    async def test_run_round_trip(self) -> None:
        result = SimpleNamespace(source_hash="HASH")
        inner = _inner(result)
        ctx = PipelineContext(original_bytes=b"data", filename="f.pdf", doc_id="DID")

        await IngestDocStage(inner).run(ctx)

        inner.run.assert_awaited_once_with(b"data", "f.pdf", "DID")
        assert ctx.ingest_result is result
        assert ctx.source_hash == "HASH"


class TestChunkStage:
    """chunk stage: ctx round-trip through its single ChunkStep."""

    def test_single_native_step(self) -> None:
        assert isinstance(ChunkStage(_inner(None)).steps[0], ChunkStep)

    @pytest.mark.asyncio
    async def test_run_round_trip(self) -> None:
        result = SimpleNamespace(chunks=["c0", "c1"])
        inner = _inner(result)
        ctx = PipelineContext(ir="IR")

        await ChunkStage(inner).run(ctx)

        inner.run.assert_awaited_once_with("IR")
        assert ctx.chunk_result is result
        assert ctx.chunks == ["c0", "c1"]


class TestContextualizeStage:
    """contextualize stage: pure-logic step ctx round-trip (no provider chain)."""

    def test_single_native_step(self) -> None:
        assert isinstance(ContextualizeStage(_inner(None)).steps[0], ContextualizeStep)

    @pytest.mark.asyncio
    async def test_run_round_trip(self) -> None:
        result = SimpleNamespace(chunks=["ctx0"])
        inner = _inner(result)
        ctx = PipelineContext(chunks=["c0"], ir="IR")

        await ContextualizeStage(inner).run(ctx)

        inner.run.assert_awaited_once_with(["c0"], "IR")
        assert ctx.contextualize_result is result
        assert ctx.chunks == ["ctx0"]


class TestMetagenStage:
    """metagen stage: ctx round-trip + the doc_meta assembly (the PR-1 IO-graph-closing fix)."""

    def test_single_native_step(self) -> None:
        assert isinstance(MetagenStage(_inner(None)).steps[0], MetagenStep)

    @pytest.mark.asyncio
    async def test_run_round_trip_and_doc_meta(self) -> None:
        ir = _fake_ir()
        result = SimpleNamespace(chunks=["meta0"], doc_fields={"summary": "x"})
        inner = _inner(result)
        ctx = PipelineContext(chunks=["c0"], ir=ir, ingest_result=SimpleNamespace(implicit_meta={}))

        await MetagenStage(inner).run(ctx)

        inner.run.assert_awaited_once_with(["c0"], ir)
        assert ctx.metagen_result is result
        assert ctx.chunks == ["meta0"]
        assert ctx.doc_fields == {"summary": "x"}
        # The metagen stage closes the IO graph by assembling doc_meta for S6.
        assert ctx.doc_meta["summary"] == "x"
        assert ctx.doc_meta["language"] == "en"
        assert ctx.doc_meta["n_figures"] == 1

    @pytest.mark.asyncio
    async def test_doc_meta_precedence(self) -> None:
        # implicit (S0) < generated (doc_fields) < user (doc_user_meta) — user always wins.
        ir = _fake_ir()
        result = SimpleNamespace(chunks=["c"], doc_fields={"k": "generated", "g": "gen_only"})
        inner = _inner(result)
        ctx = PipelineContext(
            chunks=["c"],
            ir=ir,
            ingest_result=SimpleNamespace(implicit_meta={"k": "implicit", "i": "imp_only"}),
            doc_user_meta={"k": "user"},
        )

        await MetagenStage(inner).run(ctx)

        assert ctx.doc_meta["k"] == "user"      # user overrides generated overrides implicit
        assert ctx.doc_meta["g"] == "gen_only"  # generated-only survives
        assert ctx.doc_meta["i"] == "imp_only"  # implicit-only survives


# ─── build_pipeline still yields the canonical order with these stages now native ─────────


class TestNativeStagesInBuildPipeline:
    """build_pipeline yields the canonical order; the four migrated stages are NATIVE types."""

    def test_order_unchanged_and_stages_native(self) -> None:
        registry = ProviderRegistry(s3=MagicMock(), provider_cache=MagicMock(), runtime_config=RUNTIME_CONFIG)
        dp = build_default_pipeline(RUNTIME_CONFIG)
        deps = StageDeps(s3=MagicMock(), postgres=MagicMock(), chunk_repo=MagicMock())
        stages = build_pipeline(dp, registry, deps, qdrant=MagicMock())

        assert [s.SPEC.key for s in stages] == _CANONICAL_ORDER
        by_key = {s.SPEC.key: s for s in stages}
        # Each migrated stage is the native type wrapping the same legacy implementation.
        assert isinstance(by_key["ingest"], IngestDocStage)
        assert isinstance(by_key["ingest"]._inner, S0IngestStage)
        assert isinstance(by_key["chunk"], ChunkStage)
        assert isinstance(by_key["chunk"]._inner, S4ChunkStage)
        assert isinstance(by_key["contextualize"], ContextualizeStage)
        assert isinstance(by_key["contextualize"]._inner, S5ContextualizeStage)
        assert isinstance(by_key["metagen"], MetagenStage)
        assert isinstance(by_key["metagen"]._inner, S5bMetagenStage)

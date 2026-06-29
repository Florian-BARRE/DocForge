# ====== Code Summary ======
# Parity tests for the native ParsingStage (the P1b reorg exemplar that replaces the former s1
# parse adapter). They assert the migrated stage is byte-for-byte equivalent to what the adapter
# declared: identical forced ClassVars (KEY/AFTER/IO/cache/error/NODE_TYPE/NODE_VERSION), identical
# fingerprint_params (the parse_chain signature, NOT the inherited step-aggregate), the same
# ctx round-trip (reads s0_result + the parse-node fingerprint, writes s1_result + ir), and that
# build_pipeline still yields the canonical 7-stage topo order with parse now a native ParsingStage.
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
from common_libs.pipeline.ingest.stages.parsing import ParseStep, ParsingStage
from common_libs.pipeline.stages.context import PipelineContext, StageDeps
from common_libs.pipeline.stages.s1_parse.core import S1ParseStage

_CANONICAL_ORDER = ["ingest", "parse", "enrich", "chunk", "contextualize", "metagen", "embed_index"]


def _parser_mock(signature: str = "docling:1.0,mineru:0.3", ir: str = "IR") -> MagicMock:
    """Build a mock S1ParseStage: an async run() returning an IR-bearing result + a chain signature."""
    parser = MagicMock()
    parser.run = AsyncMock(return_value=SimpleNamespace(ir=ir))
    parser.parse_chain = MagicMock()
    parser.parse_chain.signature = MagicMock(return_value=signature)
    return parser


class TestParsingStageClassVars:
    """The native ParsingStage declares the exact contract the former s1 adapter did."""

    def test_identity_and_io(self) -> None:
        assert ParsingStage.KEY == "parse"
        assert ParsingStage.NAME == "Parse"
        assert ParsingStage.AFTER == ("ingest",)
        assert ParsingStage.CONFIG is None
        assert ParsingStage.CONSUMES == ("s0_result",)
        assert ParsingStage.PRODUCES == ("s1_result", "ir")

    def test_policies_and_node_identity(self) -> None:
        # NODE_TYPE "s1" + NODE_VERSION "1.0" are the legacy cache identity (byte-identical keys).
        assert ParsingStage.CACHE_POLICY == CachePolicy.NODE_CACHED
        assert ParsingStage.ON_ERROR == ErrorPolicy.FAIL_DOC
        assert ParsingStage.NODE_TYPE == "s1"
        assert ParsingStage.NODE_VERSION == "1.0"

    def test_node_type_property_pins_legacy_s1(self) -> None:
        assert ParsingStage(_parser_mock()).node_type == "s1"


class TestParsingStageFingerprint:
    """fingerprint_params surfaces the parse_chain signature, exactly like the old adapter."""

    def test_fingerprint_params_is_parse_chain_signature(self) -> None:
        params = ParsingStage(_parser_mock(signature="docling:1.0")).fingerprint_params()
        assert params == {"parse_chain": "docling:1.0"}


class TestParsingStageRoundTrip:
    """The stage threads ctx <-> the parse implementation through its single ParseStep."""

    def test_single_native_parse_step(self) -> None:
        stage = ParsingStage(_parser_mock())
        assert len(stage.steps) == 1
        assert isinstance(stage.steps[0], ParseStep)

    @pytest.mark.asyncio
    async def test_run_reads_fingerprint_and_writes_produces(self) -> None:
        parser = _parser_mock(ir="IR")
        result = parser.run.return_value
        ctx = PipelineContext(s0_result=object())
        # The parse-node fingerprint keys the markdown blob — the step must read its OWN node key
        # ("parse"), never the upstream ingest key (legacy run_s1 passed s1_fp for this reason).
        ctx.fingerprints["parse"] = "PARSE_FP"
        ctx.fingerprints["ingest"] = "INGEST_FP"  # must be ignored

        await ParsingStage(parser).run(ctx)

        parser.run.assert_awaited_once_with(ctx.s0_result, "PARSE_FP")
        assert ctx.s1_result is result
        assert ctx.ir == "IR"


class TestParsingStageInBuildPipeline:
    """build_pipeline yields the canonical order with parse now a NATIVE ParsingStage."""

    def test_order_unchanged_and_parse_is_native(self) -> None:
        registry = ProviderRegistry(s3=MagicMock(), provider_cache=MagicMock(), runtime_config=RUNTIME_CONFIG)
        dp = build_default_pipeline(RUNTIME_CONFIG)
        deps = StageDeps(s3=MagicMock(), postgres=MagicMock(), chunk_repo=MagicMock())
        stages = build_pipeline(dp, registry, deps, qdrant=MagicMock())

        assert [s.KEY for s in stages] == _CANONICAL_ORDER
        by_key = {s.KEY: s for s in stages}
        # parse is the native stage (not an adapter) wrapping the same legacy parse implementation.
        assert isinstance(by_key["parse"], ParsingStage)
        assert isinstance(by_key["parse"]._inner, S1ParseStage)

    def test_native_parse_chain_signature_matches_builder(self) -> None:
        registry = ProviderRegistry(s3=MagicMock(), provider_cache=MagicMock(), runtime_config=RUNTIME_CONFIG)
        dp = build_default_pipeline(RUNTIME_CONFIG)
        deps = StageDeps(s3=MagicMock(), postgres=MagicMock(), chunk_repo=MagicMock())
        by_key = {s.KEY: s for s in build_pipeline(dp, registry, deps, qdrant=MagicMock())}

        # The inner parse chain signature is identical to invoking the shared builder directly,
        # and the stage's fingerprint_params surfaces exactly that signature (legacy parity).
        builder_sig = registry._build_parser_chain(dp.parse.chain, dp.parse.gate).signature()
        assert by_key["parse"]._inner.parse_chain.signature() == builder_sig
        assert by_key["parse"].fingerprint_params() == {"parse_chain": builder_sig}

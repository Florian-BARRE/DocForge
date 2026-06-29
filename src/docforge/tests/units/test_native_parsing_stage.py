# ====== Code Summary ======
# Tests for the native ParsingStage decomposed into THREE real steps: ParseStep (drive the parser
# chain → canonical IR + lineage), FigureRenderStep (crop + dedup-upload + patch figure crops), and
# MarkdownStep (serialise + upload markdown, assemble the ParseResult). They assert: the stage's
# forced ClassVars + node identity (key=parse, code_version 1.0), the parse-chain fingerprint params
# (NOT the inherited step-aggregate), the three steps' declared IO, each step's behaviour (chain
# routing + trace stamping + degraded empty-IR; figure-crop dedup + IR patch; markdown key from the
# parse-node fingerprint + ParseResult assembly + degraded markdown_key=None), the end-to-end stage
# round-trip, and build_pipeline parity (the parse chain signature is identical to the shared
# builder). Everything is mocked — no live stack.

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
from common_libs.pipeline.ingest.stages.parsing import (
    FigureRenderStep,
    MarkdownStep,
    ParseResources,
    ParseResult,
    ParseStep,
    ParsingStage,
)
from common_libs.pipeline.ingest.stages.parsing.scratch import PARSE_SCRATCH_KEY, ParseScratch
from common_libs.pipeline.stages.context import PipelineContext, StageDeps

_CANONICAL_ORDER = ["ingest", "parse", "enrich", "chunk", "contextualize", "metagen", "embed_index"]


def _chain_mock(signature: str = "docling:1.0,mineru:0.3", providers: list | None = None) -> MagicMock:
    """Build a mock parser Chain: a signature + a providers list (call() is set per-test)."""
    chain = MagicMock()
    chain.signature = MagicMock(return_value=signature)
    chain.providers = providers if providers is not None else []
    chain.call = AsyncMock()
    return chain


def _outcome(result: object, final_provider: str = "docling", degraded: bool = False) -> SimpleNamespace:
    """A minimal ChainOutcome stand-in (the fields ParseStep + ParseHelpers read)."""
    return SimpleNamespace(
        result=result, attempts=[], final_provider=final_provider, degraded=degraded
    )


def _ingest_result(pdf_bytes: bytes = b"PDF", doc_id: str = "DID") -> SimpleNamespace:
    """A minimal IngestResult stand-in exposing the fields the parse steps read."""
    return SimpleNamespace(pdf_bytes=pdf_bytes, doc_id=doc_id, source_hash="HASH", page_count=3)


def _resources(chain: MagicMock | None = None, s3: MagicMock | None = None) -> ParseResources:
    """Build a ParseResources bundle with a mocked parser chain + object store."""
    return ParseResources(
        parse_chain=chain if chain is not None else _chain_mock(),
        s3=s3 if s3 is not None else MagicMock(upload=AsyncMock()),
    )


class TestParsingStageClassVars:
    """The native ParsingStage declares the exact contract the former s1 adapter did."""

    def test_identity_and_io(self) -> None:
        assert ParsingStage.SPEC.key == "parse"
        assert ParsingStage.SPEC.name == "Parse"
        assert ParsingStage.SPEC.after == ("ingest",)
        assert ParsingStage.CONFIG is None
        assert ParsingStage.SPEC.consumes == ("ingest_result",)
        assert ParsingStage.SPEC.produces == ("parse_result", "ir")

    def test_policies_and_node_identity(self) -> None:
        # The node cache keys on the StageKey (parse) + code_version "1.0".
        assert ParsingStage.SPEC.cache_policy == CachePolicy.NODE_CACHED
        assert ParsingStage.SPEC.error_policy == ErrorPolicy.FAIL_DOC
        assert ParsingStage.SPEC.key == "parse"
        assert ParsingStage.SPEC.code_version == "1.0"

    def test_node_key_pins_legacy_s1(self) -> None:
        assert ParsingStage(_resources()).key == "parse"


class TestParsingStageFingerprint:
    """fingerprint_params surfaces the parse_chain signature, exactly like the old adapter."""

    def test_fingerprint_params_is_parse_chain_signature(self) -> None:
        params = ParsingStage(_resources(chain=_chain_mock(signature="docling:1.0"))).fingerprint_params()
        assert params == {"parse_chain": "docling:1.0"}


class TestParsingStageStructure:
    """The stage assembles three real steps in order with the declared per-step IO."""

    def test_three_native_steps_in_order(self) -> None:
        steps = ParsingStage(_resources()).steps
        assert [type(s) for s in steps] == [ParseStep, FigureRenderStep, MarkdownStep]

    def test_step_io_contracts(self) -> None:
        assert ParseStep.CONSUMES == ("ingest_result",)
        assert ParseStep.PRODUCES == ("ir", PARSE_SCRATCH_KEY)
        assert FigureRenderStep.CONSUMES == ("ingest_result", "ir", PARSE_SCRATCH_KEY)
        assert FigureRenderStep.PRODUCES == ("ir", PARSE_SCRATCH_KEY)
        assert MarkdownStep.CONSUMES == ("ir", "ingest_result", PARSE_SCRATCH_KEY)
        assert MarkdownStep.PRODUCES == ("parse_result",)


class TestParseStep:
    """The parse step routes the chain, stamps the trace, and handles the degraded case."""

    @pytest.mark.asyncio
    async def test_runs_chain_and_writes_ir(self) -> None:
        # The provider IR is a real-ish stand-in with an empty chain_traces + a model_copy that
        # records the stamped trace (so we can assert the parse trace was appended).
        stamped = {}

        def _model_copy(update: dict) -> object:
            stamped.update(update)
            return SimpleNamespace(blocks=[], chain_traces=update.get("chain_traces", []))

        provider_ir = SimpleNamespace(chain_traces=[], blocks=[], model_copy=_model_copy)
        chain = _chain_mock()
        chain.call.return_value = _outcome(result=provider_ir, final_provider="docling")
        ctx = PipelineContext(ingest_result=_ingest_result())

        await ParseStep(chain).run(ctx)

        chain.call.assert_awaited_once()
        # The IR was stamped with a parse ChainTrace and written onto the context.
        assert "chain_traces" in stamped and stamped["chain_traces"][0].stage == "parse"
        assert ctx.aux[PARSE_SCRATCH_KEY].degraded is False
        assert ctx.ir is not None

    @pytest.mark.asyncio
    async def test_degraded_outcome_substitutes_empty_ir(self) -> None:
        chain = _chain_mock()
        chain.call.return_value = _outcome(result=None, final_provider=None, degraded=True)
        ctx = PipelineContext(ingest_result=_ingest_result())

        await ParseStep(chain).run(ctx)

        # A None result (failure_policy=continue) substitutes a real empty IR (0 blocks) + degraded flag.
        assert ctx.aux[PARSE_SCRATCH_KEY].degraded is True
        assert ctx.ir.blocks == []
        assert ctx.ir.quality_score == 0.0

    def test_fingerprint_and_describe_surface_chain(self) -> None:
        provider = SimpleNamespace(name="docling", version="1.0")
        chain = _chain_mock(signature="docling:1.0", providers=[provider])
        step = ParseStep(chain)
        assert step.fingerprint_params() == {"parse_chain": "docling:1.0"}
        schema = step.describe()
        assert schema.kind == "chain"
        assert schema.category == "parse"
        assert schema.providers == ["docling"]


class TestFigureRenderStep:
    """The figure-render step crops figures, dedups + uploads them, and patches the IR."""

    @pytest.mark.asyncio
    async def test_no_figures_uploads_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # An IR with no figure blocks → the sync renderer yields no crops → no uploads, empty keys.
        s3 = MagicMock(upload=AsyncMock())
        step = FigureRenderStep(s3)
        # Stub the sync renderer so the test never needs PyMuPDF.
        monkeypatch.setattr(step, "_render_figure_crops_sync", lambda pdf, ir: [])
        ir = SimpleNamespace(blocks=[], model_copy=lambda update: SimpleNamespace(blocks=[]))
        ctx = PipelineContext(ingest_result=_ingest_result(), ir=ir)
        ctx.aux[PARSE_SCRATCH_KEY] = ParseScratch(degraded=False)

        await step.run(ctx)

        s3.upload.assert_not_awaited()
        assert ctx.aux[PARSE_SCRATCH_KEY].figure_crop_keys == {}

    @pytest.mark.asyncio
    async def test_dedups_identical_crops(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Two blocks sharing one content-addressed key must issue exactly ONE upload.
        s3 = MagicMock(upload=AsyncMock())
        step = FigureRenderStep(s3)
        crops = [("b0", "figures/by-hash/ab/abc.png", b"PNG"), ("b1", "figures/by-hash/ab/abc.png", b"PNG")]
        monkeypatch.setattr(step, "_render_figure_crops_sync", lambda pdf, ir: crops)
        patched = SimpleNamespace(blocks=[])
        ir = SimpleNamespace(blocks=[], model_copy=lambda update: patched)
        ctx = PipelineContext(ingest_result=_ingest_result(), ir=ir)
        ctx.aux[PARSE_SCRATCH_KEY] = ParseScratch(degraded=False)

        await step.run(ctx)

        s3.upload.assert_awaited_once()                         # dedup: 2 blocks → 1 blob
        keys = ctx.aux[PARSE_SCRATCH_KEY].figure_crop_keys
        assert keys == {"b0": "figures/by-hash/ab/abc.png", "b1": "figures/by-hash/ab/abc.png"}
        assert ctx.ir is patched                                # the IR was patched with the crop keys


class TestMarkdownStep:
    """The markdown step serialises + uploads markdown and assembles the ParseResult."""

    @pytest.mark.asyncio
    async def test_uploads_markdown_and_assembles_result(self) -> None:
        s3 = MagicMock(upload=AsyncMock())
        step = MarkdownStep(s3)
        # Stub the serialiser so no real IR serialisation is needed.
        step._md_serializer = SimpleNamespace(serialize=lambda ir: "# markdown")
        ir = SimpleNamespace(blocks=[])
        ctx = PipelineContext(ingest_result=_ingest_result(), ir=ir)
        ctx.aux[PARSE_SCRATCH_KEY] = ParseScratch(degraded=False, figure_crop_keys={"b0": "k0"})
        # The markdown blob is keyed by THIS node's (parse) fingerprint — never the upstream ingest one.
        ctx.fingerprints["parse"] = "PARSE_FP"
        ctx.fingerprints["ingest"] = "INGEST_FP"

        await step.run(ctx)

        s3.upload.assert_awaited_once()
        result = ctx.parse_result
        assert isinstance(result, ParseResult)
        assert result.markdown_key is not None and "PARSE_FP" in result.markdown_key
        assert result.figure_crop_keys == {"b0": "k0"}
        assert result.ir is ir

    @pytest.mark.asyncio
    async def test_degraded_skips_markdown(self) -> None:
        s3 = MagicMock(upload=AsyncMock())
        ctx = PipelineContext(ingest_result=_ingest_result(), ir=SimpleNamespace(blocks=[]))
        ctx.aux[PARSE_SCRATCH_KEY] = ParseScratch(degraded=True)

        await MarkdownStep(s3).run(ctx)

        # Degraded (no-parse) → no markdown upload, markdown_key=None, empty crops (legacy parity).
        s3.upload.assert_not_awaited()
        assert ctx.parse_result.markdown_key is None
        assert ctx.parse_result.figure_crop_keys == {}


class TestParsingStageEndToEnd:
    """The stage runs its three steps in order, producing the ParseResult feeding enrich."""

    @pytest.mark.asyncio
    async def test_full_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A provider IR whose model_copy returns an IR with zero figure/blocks so figure-render is a
        # no-op and markdown serialises a stub — exercising all three steps end to end.
        ir_after = SimpleNamespace(blocks=[], figure_blocks=[], chain_traces=[])
        ir_after.model_copy = lambda update: ir_after
        provider_ir = SimpleNamespace(chain_traces=[], blocks=[], figure_blocks=[], model_copy=lambda update: ir_after)
        chain = _chain_mock()
        chain.call.return_value = _outcome(result=provider_ir, final_provider="docling")
        s3 = MagicMock(upload=AsyncMock())
        stage = ParsingStage(_resources(chain=chain, s3=s3))
        # Stub the figure renderer (no PyMuPDF) + the markdown serialiser (no real IR serialisation).
        monkeypatch.setattr(stage.steps[1], "_render_figure_crops_sync", lambda pdf, ir: [])
        stage.steps[2]._md_serializer = SimpleNamespace(serialize=lambda ir: "# md")
        ctx = PipelineContext(ingest_result=_ingest_result())
        ctx.fingerprints["parse"] = "PARSE_FP"

        await stage.run(ctx)

        assert isinstance(ctx.parse_result, ParseResult)
        assert ctx.ir is ir_after
        s3.upload.assert_awaited_once()                 # only the markdown upload (no figures)


class TestParsingStageInBuildPipeline:
    """build_pipeline yields the canonical order with parse now a NATIVE three-step ParsingStage."""

    def test_order_unchanged_and_parse_is_native(self) -> None:
        registry = ProviderRegistry(s3=MagicMock(), provider_cache=MagicMock(), runtime_config=RUNTIME_CONFIG)
        dp = build_default_pipeline(RUNTIME_CONFIG)
        deps = StageDeps(s3=MagicMock(), postgres=MagicMock(), chunk_repo=MagicMock())
        stages = build_pipeline(dp, registry, deps, qdrant=MagicMock())

        assert [s.SPEC.key for s in stages] == _CANONICAL_ORDER
        by_key = {s.SPEC.key: s for s in stages}
        # parse is the native three-step stage carrying a ParseResources bundle.
        assert isinstance(by_key["parse"], ParsingStage)
        assert isinstance(by_key["parse"]._resources, ParseResources)
        assert [type(s) for s in by_key["parse"].steps] == [ParseStep, FigureRenderStep, MarkdownStep]

    def test_native_parse_chain_signature_matches_builder(self) -> None:
        registry = ProviderRegistry(s3=MagicMock(), provider_cache=MagicMock(), runtime_config=RUNTIME_CONFIG)
        dp = build_default_pipeline(RUNTIME_CONFIG)
        deps = StageDeps(s3=MagicMock(), postgres=MagicMock(), chunk_repo=MagicMock())
        by_key = {s.SPEC.key: s for s in build_pipeline(dp, registry, deps, qdrant=MagicMock())}

        # The parse chain signature is identical to invoking the shared builder directly, and the
        # stage's fingerprint_params surfaces exactly that signature (legacy node-cache parity).
        builder_sig = registry._build_parser_chain(dp.parse.chain, dp.parse.gate).signature()
        assert by_key["parse"]._resources.parse_chain.signature() == builder_sig
        assert by_key["parse"].fingerprint_params() == {"parse_chain": builder_sig}

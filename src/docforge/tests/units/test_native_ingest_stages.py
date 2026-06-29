# ====== Code Summary ======
# Tests for the native ingest stages. The ingest (S0) stage is decomposed into THREE real steps
# (ContentAddressStep -> ConvertStep -> ProbeStep); chunk/contextualize/metagen remain single
# delegating steps. The ingest tests assert: the three steps run in order, each step's declared
# IO + behaviour (sha256 + original upload; PDF route native/office/unknown + PDF upload; OCR-fork
# probe + implicit_meta + IngestResult assembly), the converter-identity fingerprint params, and
# end-to-end output parity (the IngestResult fields feeding parse). The chunk/contextualize/metagen
# tests assert their single-step ctx round-trip + the metagen doc_meta merge precedence. build_pipeline
# still yields the canonical 7-stage topo order with these stages native. Everything is mocked.

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
from common_libs.pipeline.ingest.stages.ingest import (
    ContentAddressStep,
    ConvertStep,
    IngestDocStage,
    IngestResources,
    IngestResult,
    ProbeStep,
)
from common_libs.pipeline.ingest.stages.ingest.scratch import INGEST_SCRATCH_KEY, IngestScratch
from common_libs.pipeline.ingest.stages.metagen import MetagenStage, MetagenStep
from common_libs.pipeline.stages.context import PipelineContext, StageDeps
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


def _mock_converter(name: str = "gotenberg", version: str = "8") -> MagicMock:
    """A mock GotenbergConverter exposing name/version + an awaitable convert()."""
    converter = MagicMock()
    converter.name = name
    converter.version = version
    converter.convert = AsyncMock()
    return converter


def _resources(s3: MagicMock | None = None, converter: MagicMock | None = None) -> IngestResources:
    """Build an IngestResources bundle with mocked object store + converter."""
    s3 = s3 if s3 is not None else MagicMock(upload=AsyncMock())
    return IngestResources(s3=s3, converter=converter if converter is not None else _mock_converter())


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
        assert IngestDocStage(_resources()).key == "ingest"


# ─── Ingest stage: the three real steps + their IO + end-to-end output parity ─────────────


class TestIngestStageStructure:
    """The ingest stage assembles three real steps in order with the declared per-step IO."""

    def test_three_native_steps_in_order(self) -> None:
        steps = IngestDocStage(_resources()).steps
        assert [type(s) for s in steps] == [ContentAddressStep, ConvertStep, ProbeStep]

    def test_step_io_contracts(self) -> None:
        assert ContentAddressStep.CONSUMES == ("original_bytes", "filename", "doc_id")
        assert ContentAddressStep.PRODUCES == ("source_hash", INGEST_SCRATCH_KEY)
        assert ConvertStep.CONSUMES == ("original_bytes", "filename", INGEST_SCRATCH_KEY)
        assert ConvertStep.PRODUCES == (INGEST_SCRATCH_KEY,)
        assert ProbeStep.CONSUMES == ("original_bytes", "filename", INGEST_SCRATCH_KEY)
        assert ProbeStep.PRODUCES == ("ingest_result",)

    def test_fingerprint_params_surfaces_converter(self) -> None:
        stage = IngestDocStage(_resources(converter=_mock_converter("gotenberg", "8")))
        assert stage.fingerprint_params() == {"converter_name": "gotenberg", "converter_version": "8"}


class TestContentAddressStep:
    """The content-address step hashes the original, uploads it, and seeds the scratch."""

    @pytest.mark.asyncio
    async def test_hash_upload_and_seed_scratch(self) -> None:
        import hashlib

        s3 = MagicMock(upload=AsyncMock())
        ctx = PipelineContext(original_bytes=b"hello", filename="report.docx", doc_id="DID")

        await ContentAddressStep(s3).run(ctx)

        # sha256("hello") is deterministic — the content address must equal it.
        expected_hash = hashlib.sha256(b"hello").hexdigest()
        assert ctx.source_hash == expected_hash
        scratch = ctx.aux[INGEST_SCRATCH_KEY]
        assert scratch.doc_id == "DID"
        assert scratch.source_hash == expected_hash
        assert scratch.original_format == "docx"
        assert scratch.original_key.endswith(expected_hash)
        s3.upload.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mints_doc_id_when_absent(self) -> None:
        ctx = PipelineContext(original_bytes=b"x", filename="f.pdf", doc_id=None)
        await ContentAddressStep(MagicMock(upload=AsyncMock())).run(ctx)
        # A None doc_id is replaced by a freshly minted UUID string (parity with legacy S0).
        assert ctx.aux[INGEST_SCRATCH_KEY].doc_id


class TestConvertStep:
    """The convert step routes by format, uploads the derived PDF, and fills the scratch."""

    def _ctx_with_scratch(self, filename: str, fmt: str, original_bytes: bytes = b"src") -> PipelineContext:
        ctx = PipelineContext(original_bytes=original_bytes, filename=filename)
        ctx.aux[INGEST_SCRATCH_KEY] = IngestScratch(
            doc_id="DID", source_hash="HASH", original_format=fmt, original_key="originals/HASH"
        )
        return ctx

    @pytest.mark.asyncio
    async def test_native_pdf_passes_through(self) -> None:
        converter = _mock_converter()
        ctx = self._ctx_with_scratch("f.pdf", "pdf", original_bytes=b"PDFDATA")
        s3 = MagicMock(upload=AsyncMock())

        await ConvertStep(s3, converter).run(ctx)

        scratch = ctx.aux[INGEST_SCRATCH_KEY]
        assert scratch.pdf_bytes == b"PDFDATA"          # passthrough — original bytes reused
        assert scratch.pdf_key.endswith("HASH/pdf")
        converter.convert.assert_not_awaited()          # native PDFs never hit Gotenberg
        s3.upload.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_office_routes_to_converter(self) -> None:
        converter = _mock_converter()
        converter.convert.return_value = SimpleNamespace(pdf_bytes=b"CONVERTED", page_count=5)
        ctx = self._ctx_with_scratch("f.docx", "docx", original_bytes=b"DOCX")

        await ConvertStep(MagicMock(upload=AsyncMock()), converter).run(ctx)

        scratch = ctx.aux[INGEST_SCRATCH_KEY]
        assert scratch.pdf_bytes == b"CONVERTED"
        assert scratch.page_count == 5
        converter.convert.assert_awaited_once_with(b"DOCX", "f.docx")

    @pytest.mark.asyncio
    async def test_unknown_format_passes_through_without_converter(self) -> None:
        converter = _mock_converter()
        ctx = self._ctx_with_scratch("f.xyz", "xyz", original_bytes=b"RAW")

        await ConvertStep(MagicMock(upload=AsyncMock()), converter).run(ctx)

        assert ctx.aux[INGEST_SCRATCH_KEY].pdf_bytes == b"RAW"   # degraded passthrough
        converter.convert.assert_not_awaited()


class TestProbeStep:
    """The probe step detects the OCR fork, builds implicit_meta, and emits the IngestResult."""

    @pytest.mark.asyncio
    async def test_assembles_ingest_result(self) -> None:
        ctx = PipelineContext(original_bytes=b"abc", filename="report.docx")
        ctx.aux[INGEST_SCRATCH_KEY] = IngestScratch(
            doc_id="DID",
            source_hash="HASH",
            original_format="docx",
            original_key="originals/HASH",
            pdf_bytes=b"PDF",
            pdf_key="derived/HASH/pdf",
            page_count=4,
        )

        await ProbeStep().run(ctx)

        result = ctx.ingest_result
        assert isinstance(result, IngestResult)
        assert result.doc_id == "DID"
        assert result.source_hash == "HASH"
        assert result.original_format == "docx"
        assert result.pdf_bytes == b"PDF"
        assert result.page_count == 4
        assert result.file_size == 3                    # len(b"abc")
        # Fake PDF bytes make the PyMuPDF probe fall back → no raster pages detected.
        assert result.needs_ocr is False
        # implicit_meta packages the file-intrinsic fields the downstream stages read.
        assert result.implicit_meta == {
            "filename": "report.docx",
            "extension": "docx",
            "file_size": 3,
            "source_hash": "HASH",
            "page_count": 4,
            "has_scanned_pages": False,
        }


class TestIngestStageEndToEnd:
    """The stage runs its three steps in order, producing the IngestResult that feeds parse."""

    @pytest.mark.asyncio
    async def test_native_pdf_full_run(self) -> None:
        import hashlib

        s3 = MagicMock(upload=AsyncMock())
        stage = IngestDocStage(_resources(s3=s3, converter=_mock_converter()))
        ctx = PipelineContext(original_bytes=b"PDFBYTES", filename="doc.pdf", doc_id="DID")

        await stage.run(ctx)

        assert ctx.source_hash == hashlib.sha256(b"PDFBYTES").hexdigest()
        result = ctx.ingest_result
        assert result.doc_id == "DID"
        assert result.original_format == "pdf"
        assert result.pdf_bytes == b"PDFBYTES"          # native passthrough survives end-to-end
        assert result.original_filename == "doc.pdf"
        # Two uploads: the original then the derived PDF.
        assert s3.upload.await_count == 2

    @pytest.mark.asyncio
    async def test_office_full_run_uses_converter(self) -> None:
        converter = _mock_converter()
        converter.convert.return_value = SimpleNamespace(pdf_bytes=b"CONVERTED", page_count=7)
        stage = IngestDocStage(_resources(converter=converter))
        ctx = PipelineContext(original_bytes=b"DOCXBYTES", filename="doc.docx", doc_id="DID")

        await stage.run(ctx)

        result = ctx.ingest_result
        assert result.pdf_bytes == b"CONVERTED"
        assert result.page_count == 7
        converter.convert.assert_awaited_once_with(b"DOCXBYTES", "doc.docx")


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
    """build_pipeline yields the canonical order; the migrated stages are NATIVE types."""

    def test_order_unchanged_and_stages_native(self) -> None:
        registry = ProviderRegistry(s3=MagicMock(), provider_cache=MagicMock(), runtime_config=RUNTIME_CONFIG)
        dp = build_default_pipeline(RUNTIME_CONFIG)
        deps = StageDeps(s3=MagicMock(), postgres=MagicMock(), chunk_repo=MagicMock())
        stages = build_pipeline(dp, registry, deps, qdrant=MagicMock())

        assert [s.SPEC.key for s in stages] == _CANONICAL_ORDER
        by_key = {s.SPEC.key: s for s in stages}
        # The ingest stage is native (it owns its steps; no legacy inner stage).
        assert isinstance(by_key["ingest"], IngestDocStage)
        assert by_key["ingest"].fingerprint_params()["converter_name"] == "gotenberg"
        assert isinstance(by_key["chunk"], ChunkStage)
        assert isinstance(by_key["chunk"]._inner, S4ChunkStage)
        assert isinstance(by_key["contextualize"], ContextualizeStage)
        assert isinstance(by_key["contextualize"]._inner, S5ContextualizeStage)
        assert isinstance(by_key["metagen"], MetagenStage)
        assert isinstance(by_key["metagen"]._inner, S5bMetagenStage)

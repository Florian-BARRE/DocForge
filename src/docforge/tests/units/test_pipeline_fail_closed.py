# ====== Code Summary ======
# Fail-closed robustness tests for the ingestion path.  Cover the document-status guarantee
# (a stage failure flips the document to ``failed``, never leaving it readable as ingested)
# and the provider/chain contracts that must RAISE on genuine failure so the chain can
# escalate and an exhausted chain returns None:
#   1. S6Embedder raises RuntimeError when the embed chain is exhausted for a batch.
#   2. S456Runner marks the document ``failed`` and re-raises when S6 fails.
#   3. PaddleOcr / VitOnnx / LayoutLabels providers re-raise on engine failure (no masked
#      degraded result), so the provider chain records the failure and escalates.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from typing import Any

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from common_libs.providers.chain import Chain
from common_libs.providers.chain_gate import ChainGate, ChainGateConfig
from common_libs.pipeline.stages.s6_embed_index.embedder import S6Embedder

from libs.pipeline.engine import StageEngine
from libs.pipeline.orchestrator.deps import StageDeps
from libs.pipeline.orchestrator.s456_runner import S456Runner


# ─── Test doubles ────────────────────────────────────────────────────────────


class _AlwaysRaisingEmbedProvider:
    """Embed provider whose every call raises — exhausts the chain."""

    name = "boom_embed"
    version = "test"
    cost_per_call = 0.0
    dimension = 8

    async def embed(self, texts: list[str]) -> Any:
        raise RuntimeError("embed backend unreachable (simulated ReadTimeout)")


class _FakeSession:
    """Async-context-manager stand-in for an AsyncSession (no real DB)."""

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakePostgres:
    """PostgresClient stand-in exposing only session() as an async context manager."""

    def session(self) -> _FakeSession:
        return _FakeSession()


class _RecordingDocumentRepo:
    """DocumentRepository stand-in that records every status it is asked to write."""

    def __init__(self) -> None:
        self.statuses: list[str] = []

    async def update_status(self, session: Any, doc_id: uuid.UUID, status: str, **kw: Any) -> None:
        self.statuses.append(status)


class _RecordingChunkRepo:
    """ChunkRepository stand-in — records whether chunks were persisted."""

    def __init__(self) -> None:
        self.inserted = 0

    async def bulk_insert(self, session: Any, chunks: list[Any]) -> None:
        self.inserted += len(chunks)


class _StaticResult:
    """Tiny S4/S5-style result carrying a ``chunks`` attribute."""

    def __init__(self, chunks: list[Any]) -> None:
        self.chunks = chunks


class _FakeS4:
    """S4 stand-in returning a fixed chunk list."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    async def run(self, ir: Any) -> _StaticResult:
        return _StaticResult(self._chunks)


class _FakeS5:
    """S5 stand-in passing chunks through unchanged."""

    async def run(self, chunks: list[Any], ir: Any) -> _StaticResult:
        return _StaticResult(chunks)


class _FailingS6:
    """S6 stand-in whose run() always raises (simulates an exhausted embed chain)."""

    async def run(self, **kwargs: Any) -> Any:
        raise RuntimeError("S6 embed chain exhausted — none returned vectors.")


class _FakeIR:
    """Minimal IR stand-in (only the attributes S456Runner touches in these paths)."""

    doc_id = "doc"
    language = "en"
    n_pages = 1
    blocks: list[Any] = []
    figure_blocks: list[Any] = []
    table_blocks: list[Any] = []


def _deps(document_repo: _RecordingDocumentRepo, chunk_repo: Any) -> StageDeps:
    """Assemble a StageDeps with fakes; unused infra fields are set to None."""
    return StageDeps(
        s3=None,                       # type: ignore[arg-type]
        postgres=_FakePostgres(),      # type: ignore[arg-type]
        node_cache=None,               # type: ignore[arg-type]
        provider_cache=None,           # type: ignore[arg-type]
        document_repo=document_repo,   # type: ignore[arg-type]
        block_repo=None,               # type: ignore[arg-type]
        chunk_repo=chunk_repo,
    )


# ─── 1. S6Embedder raises on chain exhaustion ────────────────────────────────


@pytest.mark.asyncio
async def test_s6_embedder_raises_when_chain_exhausted() -> None:
    """An exhausted embed chain must raise RuntimeError, never return empty vectors."""
    chain: Chain[Any, Any] = Chain(
        stage="embed",
        providers=[_AlwaysRaisingEmbedProvider()],
        gate=ChainGate(ChainGateConfig(min_score=0.6)),
    )
    embedder = S6Embedder(chain, embed_batch_size=16)
    embedder.begin_run()

    with pytest.raises(RuntimeError, match="embed chain exhausted"):
        await embedder.embed_texts(["hello world"])

    # The failed batch still recorded a trace (per-substep observability).
    assert len(embedder.batch_traces) == 1
    assert embedder.batch_traces[0].final_provider is None


# ─── 2. S456Runner fail-closed document status ───────────────────────────────


@pytest.mark.asyncio
async def test_s456_marks_document_failed_when_s6_fails() -> None:
    """A live S6 failure flips the document to 'failed' and re-raises (never 'done')."""
    document_repo = _RecordingDocumentRepo()
    chunk_repo = _RecordingChunkRepo()
    runner = S456Runner(_deps(document_repo, chunk_repo))
    doc_id = uuid.uuid4()

    with pytest.raises(RuntimeError, match="exhausted"):
        await runner.run_s456(
            s4=_FakeS4([]),
            s5=_FakeS5(),
            s6=_FailingS6(),
            final_ir=_FakeIR(),
            collection_id="col-1",
            s0_result=type("S0", (), {"implicit_meta": {}})(),
            doc_id=doc_id,
            metadata_fields=None,
            doc_user_meta=None,
        )

    # Fail-closed: the failure path wrote exactly the 'failed' status.
    assert document_repo.statuses == ["failed"]


@pytest.mark.asyncio
async def test_s456_no_collection_persists_chunks_without_failing() -> None:
    """With no collection, S6 is skipped: chunks persist to Postgres, status stays clean."""
    document_repo = _RecordingDocumentRepo()
    chunk_repo = _RecordingChunkRepo()
    runner = S456Runner(_deps(document_repo, chunk_repo))
    doc_id = uuid.uuid4()

    s4_result, s5_result, s6_result = await runner.run_s456(
        s4=_FakeS4(["chunk-a", "chunk-b"]),
        s5=_FakeS5(),
        s6=None,
        final_ir=_FakeIR(),
        collection_id=None,                       # no collection → no Qdrant indexing
        s0_result=type("S0", (), {"implicit_meta": {}})(),
        doc_id=doc_id,
        metadata_fields=None,
        doc_user_meta=None,
    )

    assert s6_result is None
    assert chunk_repo.inserted == 2               # chunks persisted to Postgres
    assert document_repo.statuses == []           # no failed-flip on the happy path


@pytest.mark.asyncio
async def test_s456_raises_when_collection_set_but_s6_unavailable() -> None:
    """collection_id set but no S6 stage is a hard error, and marks the doc failed."""
    document_repo = _RecordingDocumentRepo()
    chunk_repo = _RecordingChunkRepo()
    runner = S456Runner(_deps(document_repo, chunk_repo))
    doc_id = uuid.uuid4()

    with pytest.raises(RuntimeError, match="S6 indexing required"):
        await runner.run_s456(
            s4=_FakeS4([]),
            s5=_FakeS5(),
            s6=None,
            final_ir=_FakeIR(),
            collection_id="col-1",
            s0_result=type("S0", (), {"implicit_meta": {}})(),
            doc_id=doc_id,
            metadata_fields=None,
            doc_user_meta=None,
        )

    assert document_repo.statuses == ["failed"]


# ─── 2b. StageEngine marks the doc failed when the original blob is missing ───


class _FailingDownloadS3:
    """S3Client stand-in whose download() always raises (original blob missing)."""

    async def download(self, key: str) -> bytes:
        # Mirrors the real S3Client.download contract: a missing object raises KeyError.
        raise KeyError(f"Object not found: s3://docforge-objects/{key}")


@pytest.mark.asyncio
async def test_engine_marks_document_failed_when_original_missing() -> None:
    """A missing original blob (S3 download raises) flips the doc to 'failed' and re-raises.

    Regression for the reingest fail-closed gap: the engine downloads the original BEFORE the
    per-stage guards run, so a missing/unreadable original previously left the document stuck in
    its pre-run status (``pending`` on a reingest) — reading as "running" forever instead of a
    terminal ``failed``. The engine must mark it ``failed`` before propagating the error.
    """
    document_repo = _RecordingDocumentRepo()
    deps_postgres = _FakePostgres()
    engine = StageEngine(
        s0=None,                          # never reached — download fails first  # type: ignore[arg-type]
        s1=None,                          # type: ignore[arg-type]
        s3=_FailingDownloadS3(),          # type: ignore[arg-type]
        postgres=deps_postgres,           # type: ignore[arg-type]
        node_cache=None,                  # type: ignore[arg-type]
        provider_cache=None,              # type: ignore[arg-type]
        document_repo=document_repo,      # type: ignore[arg-type]
        block_repo=None,                  # type: ignore[arg-type]
    )
    doc_id = uuid.uuid4()

    with pytest.raises(KeyError, match="Object not found"):
        await engine.run(
            doc_id=doc_id,
            source_hash="deadbeef" * 8,
            filename="contrat_fr.docx",
            pipeline_version="v1",
            file_bytes=None,              # forces the S3 download path (arq worker path)
        )

    # Fail-closed: the missing-original path wrote exactly the 'failed' status.
    assert document_repo.statuses == ["failed"]


# ─── 3. Providers re-raise on engine failure (chain escalation) ──────────────


@pytest.mark.asyncio
async def test_paddle_ocr_reraises_on_engine_failure() -> None:
    """PaddleOCR must raise (not return empty) on engine failure so the chain escalates."""
    from common_libs.providers.ocr.paddle.provider import PaddleOcrProvider
    from common_libs.providers.results.ocr_result import OcrHint

    provider = PaddleOcrProvider()
    # Garbage bytes — Image.open will raise inside _extract_sync.
    with pytest.raises(Exception):
        await provider.extract(b"not-an-image", OcrHint(language="en"))


@pytest.mark.asyncio
async def test_layout_labels_reraises_on_analysis_failure() -> None:
    """LayoutLabels must raise on a true pixel-analysis failure (unreadable image)."""
    from common_libs.providers.classifier.layout_labels.provider import (
        LayoutLabelsClassifier,
    )

    provider = LayoutLabelsClassifier()
    # No label_hint → falls through to pixel analysis on undecodable bytes → raises.
    with pytest.raises(Exception):
        await provider.classify(b"not-an-image")


@pytest.mark.asyncio
async def test_failing_classifier_chain_escalates_then_exhausts() -> None:
    """A classifier that raises is a failed attempt; an all-raising chain returns None."""

    class _RaisingClassifier:
        name = "raises"
        version = "test"
        cost_per_call = 0.0

        async def classify(self, img_bytes: bytes) -> Any:
            raise RuntimeError("inference crashed")

    chain: Chain[Any, Any] = Chain(
        stage="classifier",
        providers=[_RaisingClassifier(), _RaisingClassifier()],
        gate=ChainGate(ChainGateConfig(min_score=0.5)),
    )
    outcome = await chain.call(lambda p: p.classify(b"x"))

    # Both providers raised → exhausted → None result, with both attempts recorded as failed.
    assert outcome.result is None
    assert outcome.final_provider is None
    assert len(outcome.attempts) == 2
    assert all(not a.succeeded and a.error for a in outcome.attempts)

# ====== Code Summary ======
# Migrated fail-closed / lifecycle coverage for the dynamic engine — the assertions that used to
# target the deleted S456Runner + StageEngine now run against WorkerEngineHooks + DynamicStageEngine:
#   - missing-original blob -> document 'failed' + re-raise (prepare, fail-closed).
#   - collection_id gate: no collection -> embed/index skipped, chunks persisted PG-only;
#     collection set but no embed/index stage built (no Qdrant) -> hard RuntimeError.
#   - mark_done / mark_failed write the terminal document status.
# (Generic ON_ERROR=FAIL_DOC -> mark_failed, topo order, node-cache hit/miss, and mark_done timing
# are covered at the engine level in test_dynamic_engine.py; persist_s012-after-enrich ordering is
# validated by the live pipeline suite.)

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from common_libs.config.pipeline import PipelineConfig
from common_libs.pipeline.stages.context import PipelineContext
from libs.pipeline.dynamic import DynamicStageEngine, WorkerEngineHooks
import libs.pipeline.dynamic.engine as engine_module
from libs.pipeline.orchestrator.deps import StageDeps as LegacyStageDeps


# ─── Test doubles ────────────────────────────────────────────────────────────


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
    """ChunkRepository stand-in — records how many chunks were persisted."""

    def __init__(self) -> None:
        self.inserted = 0

    async def bulk_insert(self, session: Any, chunks: list[Any]) -> None:
        self.inserted += len(chunks)


class _FailingDownloadS3:
    """S3Client stand-in whose download() always raises (original blob missing)."""

    async def download(self, key: str) -> bytes:
        raise KeyError(f"Object not found: s3://docforge-objects/{key}")


def _legacy_deps(
    *,
    s3: Any = None,
    document_repo: Any = None,
    chunk_repo: Any = None,
) -> LegacyStageDeps:
    """Assemble a legacy StageDeps with fakes; unused infra fields are None."""
    return LegacyStageDeps(
        s3=s3,                              # type: ignore[arg-type]
        postgres=_FakePostgres(),           # type: ignore[arg-type]
        node_cache=None,                    # type: ignore[arg-type]
        provider_cache=None,                # type: ignore[arg-type]
        document_repo=document_repo,        # type: ignore[arg-type]
        block_repo=None,                    # type: ignore[arg-type]
        chunk_repo=chunk_repo,
    )


# ─── WorkerEngineHooks: prepare fail-closed + collection gate + terminal status ───


class TestWorkerEngineHooks:
    """The worker lifecycle hooks reproduce the legacy fail-closed + gate behaviour."""

    @pytest.mark.asyncio
    async def test_prepare_marks_failed_when_original_missing(self) -> None:
        document_repo = _RecordingDocumentRepo()
        hooks = WorkerEngineHooks(_legacy_deps(s3=_FailingDownloadS3(), document_repo=document_repo))
        ctx = PipelineContext(doc_id=uuid.uuid4(), source_hash="deadbeef" * 8, file_bytes=None)

        with pytest.raises(KeyError, match="Object not found"):
            await hooks.prepare(ctx)

        # Fail-closed: the missing-original path wrote exactly the 'failed' status.
        assert document_repo.statuses == ["failed"]

    @pytest.mark.asyncio
    async def test_should_run_gates_embed_index_on_collection(self) -> None:
        hooks = WorkerEngineHooks(_legacy_deps())
        embed_stage = SimpleNamespace(KEY="embed_index")
        chunk_stage = SimpleNamespace(KEY="chunk")

        # No collection -> embed/index skipped; a collection -> it runs. Other stages always run.
        assert await hooks.should_run(embed_stage, PipelineContext(collection_id=None)) is False
        assert await hooks.should_run(embed_stage, PipelineContext(collection_id="col")) is True
        assert await hooks.should_run(chunk_stage, PipelineContext(collection_id=None)) is True

    @pytest.mark.asyncio
    async def test_on_skipped_persists_chunks_pg_only(self) -> None:
        chunk_repo = _RecordingChunkRepo()
        hooks = WorkerEngineHooks(_legacy_deps(chunk_repo=chunk_repo))
        ctx = PipelineContext(chunks=["chunk-a", "chunk-b"], collection_id=None)

        await hooks.on_skipped(SimpleNamespace(KEY="embed_index"), ctx)

        # No collection -> chunks land in Postgres only (no Qdrant indexing), no status flip.
        assert chunk_repo.inserted == 2

    @pytest.mark.asyncio
    async def test_mark_done_and_mark_failed_write_terminal_status(self) -> None:
        document_repo = _RecordingDocumentRepo()
        hooks = WorkerEngineHooks(_legacy_deps(document_repo=document_repo))
        ctx = PipelineContext(doc_id=uuid.uuid4())

        await hooks.mark_done(ctx)
        await hooks.mark_failed(ctx)

        assert document_repo.statuses == ["done", "failed"]


# ─── DynamicStageEngine: collection set but no embed/index stage -> hard error ───


class TestDynamicEngineCollectionGate:
    """A collection set with no embed/index stage built (no Qdrant) must fail loudly."""

    @pytest.mark.asyncio
    async def test_raises_when_collection_set_but_no_embed_index(self, monkeypatch) -> None:
        # build_pipeline returns a stage list WITHOUT embed_index (mirrors no-Qdrant build).
        monkeypatch.setattr(
            engine_module, "build_pipeline", lambda *a, **k: [SimpleNamespace(KEY="chunk")]
        )
        engine = DynamicStageEngine(
            s3=MagicMock(), postgres=MagicMock(), node_cache=MagicMock(),
            provider_cache=MagicMock(), document_repo=MagicMock(), block_repo=MagicMock(),
            chunk_repo=MagicMock(), registry=MagicMock(), qdrant=None,
            runtime_config=RUNTIME_CONFIG,
        )

        with pytest.raises(RuntimeError, match="S6 indexing required"):
            await engine.run(
                doc_id=uuid.uuid4(),
                source_hash="deadbeef" * 8,
                filename="contrat.docx",
                pipeline_version="v1",
                collection_id="col-1",            # set, but no embed_index stage -> raise
                pipeline_config=PipelineConfig(),  # skip build_default_pipeline
            )

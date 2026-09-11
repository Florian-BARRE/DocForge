"""PreviewService — the app-side dry-run coordinator. It proves the NON-PERSISTENCE contract: a
preview reads the collection + schema, runs the graph inline, and projects a report — it never calls
a write facade (no save, no index, no store_blobs). The inline runner is stubbed here so the test
stays store-free + provider-free; the projection of a real RunBundle is covered by the projector test.
"""

import pathlib
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

_APP_DIR = str(pathlib.Path(__file__).resolve().parents[3] / "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from backend.libs.preview import PreviewService  # noqa: E402
from shared_libs.pipelines.base import NodeExecutionRecord, NodeStatus  # noqa: E402
from shared_libs.public_models import (  # noqa: E402
    Chunk,
    DocumentIR,
    IntakeResult,
    RunBundle,
    SourceDocument,
)


def _fake_collection(collection_id: uuid.UUID) -> SimpleNamespace:
    """A collection row with an EMPTY pipeline → the service falls back to the stock default blob."""
    return SimpleNamespace(
        id=collection_id,
        name="demo",
        supported_formats=["pdf", "txt"],
        max_file_size_bytes=10_000_000,
        pipeline={},
        estimate_overrides=None,
    )


def _bundle() -> RunBundle:
    return RunBundle(
        ingest=IntakeResult(source_hash="h", source_format="txt", page_count=1),
        ir=DocumentIR(doc_id="d", source_hash="h", blocks=[]),
        chunks=[Chunk(chunk_id="c0", ordinal=0, text="hello world", token_count=2)],
    )


def _record() -> NodeExecutionRecord:
    return NodeExecutionRecord(
        node_id="__root__", kind="group", status=NodeStatus.SUCCESS, duration_ms=1.0, children=[]
    )


@pytest.mark.asyncio
async def test_preview_runs_inline_and_persists_nothing(monkeypatch) -> None:
    """A preview returns chunks + cost but never touches a write facade (no DB/S3/Qdrant mutation)."""
    # 1. A database façade whose every facade is a MagicMock — we assert the WRITE ones stay untouched.
    collection_id = uuid.uuid4()
    database = MagicMock()
    database.collections.get = AsyncMock(return_value=_fake_collection(collection_id))
    database.collections.get_schema = AsyncMock(return_value=[])

    # 2. Build the service, then stub its inline runner so no real parse/provider runs.
    service = PreviewService(database, timeout_seconds=5.0, chunk_text_max_chars=1000)
    monkeypatch.setattr(service._runner, "run", AsyncMock(return_value=(_bundle(), _record())))

    # 3. Run the preview on an uploaded source.
    source = SourceDocument(filename="a.txt", content=b"hello world", declared_meta={})
    response = await service.preview(collection_id, source, max_chunks=10)

    # 4. It produced a real preview (a chunk came back).
    assert response is not None
    assert response.ok is True
    assert response.chunk_count == 1
    assert response.chunks[0].text == "hello world"

    # 5. NON-PERSISTENCE: not a single write facade was invoked by the dry-run.
    database.ingestion.save.assert_not_called()
    database.ingestion.index.assert_not_called()
    database.ingestion.store_blobs.assert_not_called()
    database.jobs.persist_execution_tree.assert_not_called()


@pytest.mark.asyncio
async def test_preview_unknown_collection_returns_none() -> None:
    """An unknown collection → None (the router maps it to a 404), no run attempted."""
    database = MagicMock()
    database.collections.get = AsyncMock(return_value=None)
    service = PreviewService(database, timeout_seconds=5.0, chunk_text_max_chars=1000)
    source = SourceDocument(filename="a.txt", content=b"x", declared_meta={})
    assert await service.preview(uuid.uuid4(), source, max_chunks=5) is None

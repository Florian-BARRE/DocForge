# ====== Code Summary ======
# Guard tests for the worker preview job (jobs.preview.preview_pipeline) — the central invariant is
# NON-PERSISTENCE: a dry-run must never write a document/chunk row, an S3 blob, a Qdrant point, or an
# execution-tree row. These tests run the task with a fully-mocked CONTEXT (the engine run itself is
# stubbed — the heavy deps are not present in a unit env) and assert (1) NO write facade method on the
# Database was ever called, and (2) a pre-run failure (unknown collection / bad input) is DATA (a
# PreviewResponse with ok=false), never a raised exception.

# ====== Standard Library Imports ======
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeExecutionRecord, NodeStatus
from shared_libs.public_models import IntakeResult, RunBundle
from shared_libs.public_models.ir import DocumentIR

# The Database write methods a preview must NEVER touch — the non-persistence contract, enumerated.
_FORBIDDEN_WRITES = [
    ("ingestion", "save"),
    ("ingestion", "store_blobs"),
    ("ingestion", "index"),
    ("ingestion", "mark_processing"),
    ("ingestion", "mark_failed"),
    ("ingestion", "store_trace_payloads"),
    ("jobs", "persist_execution_tree"),
    ("jobs", "mark_running"),
    ("jobs", "mark_done"),
    ("jobs", "mark_failed"),
    ("filters", "sync_document_filter_payloads"),
    ("meta_vectors", "sync_document_meta_vectors"),
]


def _fake_config() -> SimpleNamespace:
    """A minimal RUNTIME_CONFIG stand-in with the worker preview knobs the job reads."""
    return SimpleNamespace(
        WORKER_PREVIEW_RUN_TIMEOUT_SECONDS=300.0,
        WORKER_PREVIEW_MAX_CHUNKS=20,
        WORKER_PREVIEW_CHUNK_TEXT_MAX_CHARS=2000,
        WORKER_PREVIEW_MAX_BYTES=10 * 1024 * 1024,
    )


def _fake_database() -> MagicMock:
    """A Database facade whose every method is a mock — reads return stubs, writes are observable."""
    database = MagicMock()
    database.collections.get = AsyncMock(
        return_value=SimpleNamespace(
            id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            name="demo",
            supported_formats=["pdf"],
            max_file_size_bytes=10 * 1024 * 1024,
            pipeline=None,
            estimate_overrides=None,
        )
    )
    database.collections.get_schema = AsyncMock(return_value=[])
    # Every forbidden write is an AsyncMock so a stray await would register as a call (and fail).
    for facade, method in _FORBIDDEN_WRITES:
        setattr(getattr(database, facade), method, AsyncMock())
    return database


def _assert_no_writes(database: MagicMock) -> None:
    """Assert NONE of the persistence writers were ever invoked by the preview path."""
    for facade, method in _FORBIDDEN_WRITES:
        call = getattr(getattr(database, facade), method)
        assert not call.called, f"preview wrote via {facade}.{method} — non-persistence violated"


@pytest.mark.asyncio
async def test_preview_job_persists_nothing(monkeypatch, jobs_preview):
    """A successful preview returns the report dict and calls ZERO persistence writers."""
    # 1. A fully-mocked CONTEXT (reads stubbed, writes observable). The engine run is stubbed to a
    #    delivered bundle so the test isolates the non-persistence invariant from heavy parse deps.
    database = _fake_database()
    monkeypatch.setattr(
        jobs_preview,
        "CONTEXT",
        SimpleNamespace(database=database, RUNTIME_CONFIG=_fake_config(), logger=MagicMock()),
    )
    bundle = RunBundle(
        ir=DocumentIR(doc_id="d", source_hash="h", title="t", language="en", blocks=[]),
        ingest=IntakeResult(
            source_hash="h", source_format="pdf", page_count=1, source_content=b"x"
        ),
        chunks=[],
        embeddings=None,
    )
    record = NodeExecutionRecord(
        node_id="root", kind="group", status=NodeStatus.SUCCESS, duration_ms=1.0
    )
    monkeypatch.setattr(jobs_preview._RUNNER, "run", AsyncMock(return_value=(bundle, record)))

    # 2. Run the task on uploaded bytes (no store read needed).
    result = await jobs_preview.preview_pipeline(
        {},
        "preview-1",
        "11111111-1111-1111-1111-111111111111",
        content=b"%PDF-fake",
        declared_meta={},
        filename="demo.pdf",
    )

    # 3. It returned a bounded report AND wrote nothing durable.
    assert result["ok"] is True
    assert result["source_filename"] == "demo.pdf"
    _assert_no_writes(database)


@pytest.mark.asyncio
async def test_preview_job_unknown_collection_is_data(monkeypatch, jobs_preview):
    """An unknown collection is DATA (ok=false), never an exception — and writes nothing."""
    database = _fake_database()
    database.collections.get = AsyncMock(return_value=None)
    monkeypatch.setattr(
        jobs_preview,
        "CONTEXT",
        SimpleNamespace(database=database, RUNTIME_CONFIG=_fake_config(), logger=MagicMock()),
    )

    result = await jobs_preview.preview_pipeline(
        {},
        "preview-2",
        "22222222-2222-2222-2222-222222222222",
        content=b"x",
        filename="demo.pdf",
    )

    assert result["ok"] is False
    assert "not found" in result["error"]
    _assert_no_writes(database)

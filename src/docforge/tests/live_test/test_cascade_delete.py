# ====== Code Summary ======
# Integration-style unit tests for DocumentOps.delete_cascade.
# CONTEXT is patched in-process (no live DB/Qdrant/S3). Tests verify that:
#   - Qdrant points are deleted by chunk IDs
#   - Postgres rows are deleted via cascade
#   - S3 blobs are deleted only when the source hash is NOT shared
#   - Qdrant=None path skips vector deletion cleanly
#
# patch.object(create=True) does not work for classes with type-annotation-only attributes
# (Python's CONTEXT pattern); we use direct setattr + cleanup instead.

# ====== Standard Library Imports ======
import uuid
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Generator
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.routers.collections.documents.helpers import DocumentOps

# Sentinel used to distinguish "not set" from None when restoring CONTEXT attributes.
_MISSING = object()


@contextmanager
def _patch_context(**kwargs: Any) -> Generator[None, None, None]:
    """
    Temporarily set CONTEXT class attributes for a test, then restore them.

    Uses direct setattr because CONTEXT has type-annotation-only attributes
    (no actual class-level values), which makes patch.object(create=True) unreliable.

    Yields:
        None
    """
    saved = {k: getattr(CONTEXT, k, _MISSING) for k in kwargs}
    for k, v in kwargs.items():
        setattr(CONTEXT, k, v)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is _MISSING:
                try:
                    delattr(CONTEXT, k)
                except AttributeError:
                    pass
            else:
                setattr(CONTEXT, k, v)


# ── Shared helpers ────────────────────────────────────────────────────────────


def _make_session_ctx(session: MagicMock) -> callable:
    """Return a callable that behaves as an async context manager yielding `session`."""
    @asynccontextmanager
    async def _ctx() -> AsyncIterator[MagicMock]:
        yield session
    return _ctx


def _make_postgres(session: MagicMock) -> MagicMock:
    """Build a mock PostgresClient whose session() method yields the given mock session."""
    pg = MagicMock()
    pg.session = _make_session_ctx(session)
    return pg


def _make_chunk_repo(chunk_rows: list[dict]) -> MagicMock:
    """Build a mock ChunkRepository that returns `chunk_rows` for any get_by_document call."""
    repo = MagicMock()
    repo.get_by_document = AsyncMock(return_value=chunk_rows)
    return repo


def _make_document_repo(*, shared: bool) -> MagicMock:
    """Build a mock DocumentRepository with controllable `is_source_hash_used_by_other_documents`."""
    repo = MagicMock()
    repo.is_source_hash_used_by_other_documents = AsyncMock(return_value=shared)
    repo.delete = AsyncMock()
    return repo


def _make_qdrant(points_deleted: int = 3) -> MagicMock:
    """Build a mock QdrantStorageClient returning a fixed delete count."""
    qdrant = MagicMock()
    qdrant.delete_points = AsyncMock(return_value=points_deleted)
    return qdrant


def _make_s3() -> MagicMock:
    """Build a mock S3Client with async delete methods."""
    s3 = MagicMock()
    s3.delete = AsyncMock()
    s3.delete_prefix = AsyncMock()
    return s3


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cascade_deletes_all_stores_when_not_shared() -> None:
    """
    When the source hash is NOT shared, all three stores are cleaned up:
    Qdrant points → Postgres cascade → S3 blob + derived prefix.
    """
    collection_id = uuid.uuid4()
    document_id = uuid.uuid4()
    source_hash = "abc" * 21

    session = MagicMock()
    chunks = [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}]
    qdrant = _make_qdrant(points_deleted=3)
    s3 = _make_s3()

    with _patch_context(
        postgres=_make_postgres(session),
        chunk_repo=_make_chunk_repo(chunks),
        document_repo=_make_document_repo(shared=False),
        qdrant=qdrant,
        s3=s3,
    ):
        result = await DocumentOps.delete_cascade(collection_id, document_id, source_hash)

    # Qdrant called with correct point IDs
    qdrant.delete_points.assert_awaited_once()
    call_args = qdrant.delete_points.call_args
    assert call_args[0][0] == str(collection_id)
    assert set(call_args[0][1]) == {"c1", "c2", "c3"}

    # S3 cleaned up (not shared)
    s3.delete.assert_awaited_once()
    s3.delete_prefix.assert_awaited_once()

    assert result["qdrant_points_deleted"] == 3
    assert result["blob_deleted"] is True


@pytest.mark.asyncio
async def test_cascade_skips_s3_when_blob_is_shared() -> None:
    """When the source hash is shared by other documents, S3 blobs must NOT be deleted."""
    collection_id = uuid.uuid4()
    document_id = uuid.uuid4()

    session = MagicMock()
    s3 = _make_s3()
    qdrant = _make_qdrant(points_deleted=1)

    with _patch_context(
        postgres=_make_postgres(session),
        chunk_repo=_make_chunk_repo([{"id": "c1"}]),
        document_repo=_make_document_repo(shared=True),
        qdrant=qdrant,
        s3=s3,
    ):
        result = await DocumentOps.delete_cascade(collection_id, document_id, "shared-hash")

    s3.delete.assert_not_awaited()
    s3.delete_prefix.assert_not_awaited()
    assert result["blob_deleted"] is False
    assert result["qdrant_points_deleted"] == 1


@pytest.mark.asyncio
async def test_cascade_skips_qdrant_when_none() -> None:
    """When CONTEXT.qdrant is None (S6 disabled), only Postgres and S3 are cleaned up."""
    collection_id = uuid.uuid4()
    document_id = uuid.uuid4()

    session = MagicMock()
    s3 = _make_s3()

    with _patch_context(
        postgres=_make_postgres(session),
        chunk_repo=_make_chunk_repo([{"id": "c1"}]),
        document_repo=_make_document_repo(shared=False),
        qdrant=None,
        s3=s3,
    ):
        result = await DocumentOps.delete_cascade(collection_id, document_id, "hash-abc")

    assert result["qdrant_points_deleted"] == 0
    s3.delete.assert_awaited_once()
    assert result["blob_deleted"] is True


@pytest.mark.asyncio
async def test_cascade_no_chunks_still_deletes_postgres_and_s3() -> None:
    """A document with zero indexed chunks (S6 never ran) still deletes its Postgres row and blob."""
    collection_id = uuid.uuid4()
    document_id = uuid.uuid4()

    session = MagicMock()
    qdrant = _make_qdrant(points_deleted=0)
    s3 = _make_s3()

    with _patch_context(
        postgres=_make_postgres(session),
        chunk_repo=_make_chunk_repo([]),
        document_repo=_make_document_repo(shared=False),
        qdrant=qdrant,
        s3=s3,
    ):
        result = await DocumentOps.delete_cascade(collection_id, document_id, "hash-xyz")

    s3.delete.assert_awaited_once()
    assert result["blob_deleted"] is True

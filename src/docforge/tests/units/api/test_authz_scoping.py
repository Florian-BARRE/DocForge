"""Multi-tenant scope enforcement (the cross-tenant gap closure): the two AuthzGuard scope helpers
(`assert_collection_scope` / `assert_any_collection_scope`), the explorer chokepoints that apply
them (`_require_document` / `_assert_chunk_scope`), and the resource-router handlers wired to them
(jobs · blobs · explorer) — proving a key scoped to collection A is 403 on collection B's data and
allowed on A's, while a full-access (root) key is entirely unaffected.

All store access is mocked via CONTEXT.database; ``from backend...`` imports are deferred until the
``fastapi_app`` fixture has registered app/ on sys.path. The autouse fixture forces auth OFF, but
these tests call the handlers/helpers directly with an explicit principal, so the toggle is moot —
they exercise the scope logic regardless of AUTH_ENABLED.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

# Two stable collection ids — the "owned" (A) and the "foreign" (B) tenant.
COLL_A = "11111111-1111-1111-1111-111111111111"
COLL_B = "22222222-2222-2222-2222-222222222222"


# ── shared fakes ──────────────────────────────────────────────────────────────────────────────


def _principal(*, permissions):
    """Build an AuthPrincipal directly (full access iff permissions is None)."""
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    key = SimpleNamespace(permissions=permissions, revoked_at=None, user_id="user-1")
    return AuthPrincipal(
        user=SimpleNamespace(is_active=True), key=key, is_full_access=permissions is None
    )


def _scoped(collection_id: str):
    """A scoped key granting read+write on exactly one collection."""
    return _principal(
        permissions={"capabilities": ["read", "write"], "collections": [collection_id]}
    )


def _full():
    """A full-access (root / NULL-permission) principal."""
    return _principal(permissions=None)


def _fake_job(collection_id: str):
    """A stand-in Job row carrying every field the jobs router's status mapper reads."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        collection_id=uuid.UUID(collection_id),
        status=SimpleNamespace(value="done"),
        progress=100,
        current_stage="embed",
        error=None,
        attempt=1,
        started_at=None,
        finished_at=None,
        updated_at=datetime(2026, 8, 3, 12, 0, tzinfo=UTC),
        total_prompt_tokens=0,
        total_completion_tokens=0,
        cost_usd=0,
        items_done=None,
        items_total=None,
        failed_node_id=None,
        failed_node_kind=None,
        failed_item_index=None,
        error_type=None,
    )


# ── AuthzGuard.assert_collection_scope ──────────────────────────────────────────────────────────


def test_assert_collection_scope_full_access_is_noop(fastapi_app) -> None:
    from backend.libs.auth.authz import AuthzGuard  # noqa: PLC0415

    # No raise even for a collection nothing enumerates.
    AuthzGuard.assert_collection_scope(_full(), COLL_B)


def test_assert_collection_scope_matching_is_allowed(fastapi_app) -> None:
    from backend.libs.auth.authz import AuthzGuard  # noqa: PLC0415

    AuthzGuard.assert_collection_scope(_scoped(COLL_A), COLL_A)


def test_assert_collection_scope_foreign_is_403(fastapi_app) -> None:
    from backend.libs.auth.authz import AuthzGuard  # noqa: PLC0415

    with pytest.raises(HTTPException) as exc:
        AuthzGuard.assert_collection_scope(_scoped(COLL_A), COLL_B)

    assert exc.value.status_code == 403


# ── AuthzGuard.assert_any_collection_scope ──────────────────────────────────────────────────────


def test_assert_any_collection_scope_full_access_is_noop(fastapi_app) -> None:
    from backend.libs.auth.authz import AuthzGuard  # noqa: PLC0415

    AuthzGuard.assert_any_collection_scope(_full(), [])


def test_assert_any_collection_scope_owns_one_is_allowed(fastapi_app) -> None:
    from backend.libs.auth.authz import AuthzGuard  # noqa: PLC0415

    # The resource is reachable through B and A; the key owns A → allowed.
    AuthzGuard.assert_any_collection_scope(_scoped(COLL_A), [COLL_B, COLL_A])


def test_assert_any_collection_scope_owns_none_is_403(fastapi_app) -> None:
    from backend.libs.auth.authz import AuthzGuard  # noqa: PLC0415

    with pytest.raises(HTTPException) as exc:
        AuthzGuard.assert_any_collection_scope(_scoped(COLL_A), [COLL_B])

    assert exc.value.status_code == 403


def test_assert_any_collection_scope_empty_set_denies_scoped_key(fastapi_app) -> None:
    """An orphan/foreign blob resolves to no owned collection → the scoped key is denied."""
    from backend.libs.auth.authz import AuthzGuard  # noqa: PLC0415

    with pytest.raises(HTTPException) as exc:
        AuthzGuard.assert_any_collection_scope(_scoped(COLL_A), [])

    assert exc.value.status_code == 403


# ── explorer chokepoints (_require_document / _assert_chunk_scope) ───────────────────────────────


async def test_require_document_full_access_reaches_foreign_document(
    fastapi_app, monkeypatch
) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.explorer.router import _require_document  # noqa: PLC0415

    document = SimpleNamespace(collection_id=uuid.UUID(COLL_B))
    documents = SimpleNamespace(get=AsyncMock(return_value=document))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))

    # A root key reads a document in ANY collection.
    assert await _require_document(uuid.uuid4(), _full()) is document


async def test_require_document_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.explorer.router import _require_document  # noqa: PLC0415

    documents = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(collection_id=uuid.UUID(COLL_B)))
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))

    with pytest.raises(HTTPException) as exc:
        await _require_document(uuid.uuid4(), _scoped(COLL_A))

    assert exc.value.status_code == 403


async def test_require_document_unknown_is_404_before_scope(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.explorer.router import _require_document  # noqa: PLC0415

    documents = SimpleNamespace(get=AsyncMock(return_value=None))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))

    with pytest.raises(HTTPException) as exc:
        await _require_document(uuid.uuid4(), _scoped(COLL_A))

    assert exc.value.status_code == 404


async def test_assert_chunk_scope_full_access_skips_lookup(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.explorer.router import _assert_chunk_scope  # noqa: PLC0415

    documents = SimpleNamespace(collections_for_chunks=AsyncMock(return_value=[COLL_B]))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))

    await _assert_chunk_scope([uuid.uuid4()], _full())

    # Root bypasses the check entirely — the resolving query is never issued.
    documents.collections_for_chunks.assert_not_called()


async def test_assert_chunk_scope_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.explorer.router import _assert_chunk_scope  # noqa: PLC0415

    documents = SimpleNamespace(collections_for_chunks=AsyncMock(return_value=[COLL_B]))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))

    with pytest.raises(HTTPException) as exc:
        await _assert_chunk_scope([uuid.uuid4()], _scoped(COLL_A))

    assert exc.value.status_code == 403


async def test_assert_chunk_scope_scoped_key_owned_is_allowed(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.explorer.router import _assert_chunk_scope  # noqa: PLC0415

    documents = SimpleNamespace(collections_for_chunks=AsyncMock(return_value=[COLL_A]))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))

    await _assert_chunk_scope([uuid.uuid4()], _scoped(COLL_A))


# ── jobs router ─────────────────────────────────────────────────────────────────────────────────


async def test_get_job_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import get_job  # noqa: PLC0415

    jobs = SimpleNamespace(get=AsyncMock(return_value=_fake_job(COLL_B)))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))

    with pytest.raises(HTTPException) as exc:
        await get_job(job_id=uuid.uuid4(), principal=_scoped(COLL_A))

    assert exc.value.status_code == 403


async def test_get_job_scoped_key_owned_is_allowed(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import get_job  # noqa: PLC0415

    jobs = SimpleNamespace(get=AsyncMock(return_value=_fake_job(COLL_A)))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))

    result = await get_job(job_id=uuid.uuid4(), principal=_scoped(COLL_A))

    assert result.collection_id == COLL_A


async def test_get_job_full_access_reaches_foreign_job(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import get_job  # noqa: PLC0415

    jobs = SimpleNamespace(get=AsyncMock(return_value=_fake_job(COLL_B)))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))

    result = await get_job(job_id=uuid.uuid4(), principal=_full())

    assert result.collection_id == COLL_B


async def test_list_jobs_scoped_key_foreign_query_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import list_jobs  # noqa: PLC0415

    jobs = SimpleNamespace(list_for_collection=AsyncMock(return_value=[]))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))

    with pytest.raises(HTTPException) as exc:
        await list_jobs(collection_id=uuid.UUID(COLL_B), principal=_scoped(COLL_A))

    assert exc.value.status_code == 403
    # The scope gate fires BEFORE any read of the foreign collection's rows.
    jobs.list_for_collection.assert_not_called()


async def test_list_jobs_scoped_key_owned_query_is_allowed(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import list_jobs  # noqa: PLC0415

    jobs = SimpleNamespace(list_for_collection=AsyncMock(return_value=[]))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))

    assert await list_jobs(collection_id=uuid.UUID(COLL_A), principal=_scoped(COLL_A)) == []


async def test_get_job_trace_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import get_job_trace  # noqa: PLC0415

    jobs = SimpleNamespace(
        get=AsyncMock(return_value=_fake_job(COLL_B)), list_events=AsyncMock(return_value=[])
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))

    with pytest.raises(HTTPException) as exc:
        await get_job_trace(job_id=uuid.uuid4(), principal=_scoped(COLL_A))

    assert exc.value.status_code == 403
    jobs.list_events.assert_not_called()


# ── blobs router ────────────────────────────────────────────────────────────────────────────────


async def test_get_blob_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.blobs.router import get_blob  # noqa: PLC0415

    documents = SimpleNamespace(
        collections_for_blob=AsyncMock(return_value=[COLL_B]),
        read_blob=AsyncMock(return_value=(b"x", "text/plain")),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))

    with pytest.raises(HTTPException) as exc:
        await get_blob(content_hash="deadbeef", principal=_scoped(COLL_A))

    assert exc.value.status_code == 403
    # A denied scoped key never triggers the S3 byte fetch.
    documents.read_blob.assert_not_called()


async def test_get_blob_scoped_key_owned_is_allowed(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.blobs.router import get_blob  # noqa: PLC0415

    documents = SimpleNamespace(
        collections_for_blob=AsyncMock(return_value=[COLL_A]),
        read_blob=AsyncMock(return_value=(b"x", "text/plain")),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))

    result = await get_blob(content_hash="deadbeef", principal=_scoped(COLL_A))

    assert result.body == b"x"


async def test_get_blob_full_access_skips_scope_lookup(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.blobs.router import get_blob  # noqa: PLC0415

    documents = SimpleNamespace(
        collections_for_blob=AsyncMock(return_value=[COLL_B]),
        read_blob=AsyncMock(return_value=(b"x", "text/plain")),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))

    result = await get_blob(content_hash="deadbeef", principal=_full())

    assert result.body == b"x"
    # Root never resolves owning collections — it reads any blob directly.
    documents.collections_for_blob.assert_not_called()


# ── explorer router (document + chunk mutations) ────────────────────────────────────────────────


async def test_get_document_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.explorer.router import get_document  # noqa: PLC0415

    documents = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(collection_id=uuid.UUID(COLL_B)))
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))

    with pytest.raises(HTTPException) as exc:
        await get_document(document_id=uuid.uuid4(), principal=_scoped(COLL_A))

    assert exc.value.status_code == 403


async def test_delete_document_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.explorer.router import delete_document  # noqa: PLC0415

    documents = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(collection_id=uuid.UUID(COLL_B))),
        delete=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))

    with pytest.raises(HTTPException) as exc:
        await delete_document(document_id=uuid.uuid4(), principal=_scoped(COLL_A))

    assert exc.value.status_code == 403
    # The cross-store deletion is never reached for a foreign scoped key.
    documents.delete.assert_not_called()


async def test_set_chunk_enabled_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.explorer.models import ChunkEnabledPatch  # noqa: PLC0415
    from backend.routers.explorer.router import set_chunk_enabled  # noqa: PLC0415

    documents = SimpleNamespace(collections_for_chunks=AsyncMock(return_value=[COLL_B]))
    enablement = SimpleNamespace(set_chunks_enabled=AsyncMock(return_value=[]))
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(documents=documents, enablement=enablement)
    )

    with pytest.raises(HTTPException) as exc:
        await set_chunk_enabled(
            chunk_id=uuid.uuid4(), patch=ChunkEnabledPatch(enabled=False), principal=_scoped(COLL_A)
        )

    assert exc.value.status_code == 403
    # The toggle never fires for a chunk in a collection the key does not own.
    enablement.set_chunks_enabled.assert_not_called()

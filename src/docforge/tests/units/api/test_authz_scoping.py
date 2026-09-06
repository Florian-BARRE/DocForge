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
        cancel_requested=False,
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


def _fake_job_with_names(collection_id: str):
    """The joined read model the get/list routes consume — a job row plus its display names."""
    return SimpleNamespace(
        job=_fake_job(collection_id),
        document_filename="f.pdf",
        document_title="Doc",
        collection_name="c",
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

    jobs = SimpleNamespace(get_with_names=AsyncMock(return_value=_fake_job_with_names(COLL_B)))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))

    with pytest.raises(HTTPException) as exc:
        await get_job(job_id=uuid.uuid4(), principal=_scoped(COLL_A))

    assert exc.value.status_code == 403


async def test_get_job_scoped_key_owned_is_allowed(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import get_job  # noqa: PLC0415

    jobs = SimpleNamespace(get_with_names=AsyncMock(return_value=_fake_job_with_names(COLL_A)))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))

    result = await get_job(job_id=uuid.uuid4(), principal=_scoped(COLL_A))

    assert result.collection_id == COLL_A


async def test_get_job_full_access_reaches_foreign_job(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import get_job  # noqa: PLC0415

    jobs = SimpleNamespace(get_with_names=AsyncMock(return_value=_fake_job_with_names(COLL_B)))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))

    result = await get_job(job_id=uuid.uuid4(), principal=_full())

    assert result.collection_id == COLL_B


async def test_list_jobs_scoped_key_foreign_query_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import list_jobs  # noqa: PLC0415

    jobs = SimpleNamespace(list_for_collection_with_names=AsyncMock(return_value=[]))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))

    with pytest.raises(HTTPException) as exc:
        await list_jobs(collection_id=uuid.UUID(COLL_B), principal=_scoped(COLL_A))

    assert exc.value.status_code == 403
    # The scope gate fires BEFORE any read of the foreign collection's rows.
    jobs.list_for_collection_with_names.assert_not_called()


async def test_list_jobs_scoped_key_owned_query_is_allowed(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import list_jobs  # noqa: PLC0415

    jobs = SimpleNamespace(
        list_for_collection_with_names=AsyncMock(return_value=[]),
        count_for_collection=AsyncMock(return_value=0),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs))

    page = await list_jobs(
        collection_id=uuid.UUID(COLL_A), limit=500, offset=0, principal=_scoped(COLL_A)
    )
    assert page.total == 0 and page.jobs == []


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


async def _blob_stream():
    """A minimal async byte-stream standing in for the facade's bounded S3 windows."""
    yield b"x"


async def _drain(response) -> bytes:
    """Collect a StreamingResponse's body from its async iterator."""
    chunks = [chunk async for chunk in response.body_iterator]
    return b"".join(bytes(chunk) for chunk in chunks)


async def test_get_blob_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.blobs.router import get_blob  # noqa: PLC0415

    documents = SimpleNamespace(
        collections_for_blob=AsyncMock(return_value=[COLL_B]),
        stream_blob=AsyncMock(return_value=(_blob_stream(), "text/plain")),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))

    with pytest.raises(HTTPException) as exc:
        await get_blob(content_hash="deadbeef", principal=_scoped(COLL_A))

    assert exc.value.status_code == 403
    # A denied scoped key never triggers the S3 byte fetch.
    documents.stream_blob.assert_not_called()


async def test_get_blob_scoped_key_owned_is_allowed(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.blobs.router import get_blob  # noqa: PLC0415

    documents = SimpleNamespace(
        collections_for_blob=AsyncMock(return_value=[COLL_A]),
        stream_blob=AsyncMock(return_value=(_blob_stream(), "text/plain")),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))

    result = await get_blob(content_hash="deadbeef", principal=_scoped(COLL_A))

    assert await _drain(result) == b"x"


async def test_get_blob_full_access_skips_scope_lookup(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.blobs.router import get_blob  # noqa: PLC0415

    documents = SimpleNamespace(
        collections_for_blob=AsyncMock(return_value=[COLL_B]),
        stream_blob=AsyncMock(return_value=(_blob_stream(), "text/plain")),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(documents=documents))

    result = await get_blob(content_hash="deadbeef", principal=_full())

    assert await _drain(result) == b"x"
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


# ── documents-router IDOR closures (enable/disable + reingest carry no collection in the path) ────


async def test_set_document_enabled_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.documents.models import EnabledPatch  # noqa: PLC0415
    from backend.routers.documents.router import set_document_enabled  # noqa: PLC0415

    documents = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(collection_id=uuid.UUID(COLL_B)))
    )
    enablement = SimpleNamespace(set_document_enabled=AsyncMock(return_value=True))
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(documents=documents, enablement=enablement)
    )

    with pytest.raises(HTTPException) as exc:
        await set_document_enabled(
            document_id=uuid.uuid4(), patch=EnabledPatch(enabled=False), principal=_scoped(COLL_A)
        )

    assert exc.value.status_code == 403
    # The searchability flip never fires for a document in a collection the key does not own.
    enablement.set_document_enabled.assert_not_called()


async def test_reingest_document_scoped_key_foreign_is_403(fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.documents.router import reingest_document  # noqa: PLC0415

    documents = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(collection_id=uuid.UUID(COLL_B)))
    )
    ingestion = SimpleNamespace(reingest=AsyncMock())
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(documents=documents, ingestion=ingestion)
    )
    monkeypatch.setattr(CONTEXT, "queue", SimpleNamespace(enqueue_ingest=AsyncMock()))

    with pytest.raises(HTTPException) as exc:
        await reingest_document(document_id=uuid.uuid4(), force=False, principal=_scoped(COLL_A))

    assert exc.value.status_code == 403
    # No paid job is minted or enqueued for another tenant's document.
    ingestion.reingest.assert_not_called()
    CONTEXT.queue.enqueue_ingest.assert_not_called()


async def test_list_collections_scoped_key_sees_only_its_own(fastapi_app, monkeypatch) -> None:
    import importlib  # noqa: PLC0415

    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.collections.router import list_collections  # noqa: PLC0415

    collections_router = importlib.import_module("backend.routers.collections.router")

    coll_a = SimpleNamespace(id=uuid.UUID(COLL_A))
    coll_b = SimpleNamespace(id=uuid.UUID(COLL_B))
    collections = SimpleNamespace(
        list_all=AsyncMock(return_value=[coll_a, coll_b]),
        get_schema=AsyncMock(return_value=[]),
    )
    documents = SimpleNamespace(
        count_by_collections=AsyncMock(return_value={}),
        count_chunks_by_collections=AsyncMock(return_value={}),
    )
    jobs = SimpleNamespace(last_successful_ingest_at_by_collections=AsyncMock(return_value={}))
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(collections=collections, documents=documents, jobs=jobs),
    )
    monkeypatch.setattr(
        CONTEXT,
        "health_service",
        SimpleNamespace(summarize_structural=lambda cols, **_: {c.id: None for c in cols}),
    )
    # Bypass the Pydantic model construction — the assertion is purely about the scope filter.
    monkeypatch.setattr(
        collections_router.CollectionHelpers,
        "to_model",
        staticmethod(lambda c, schema: SimpleNamespace(model_dump=lambda: {"id": str(c.id)})),
    )
    monkeypatch.setattr(collections_router, "CollectionListItem", lambda **kw: kw.get("id"))

    result = await list_collections(principal=_scoped(COLL_A))

    # Only collection A survives the scope filter; B's contract never leaves the server.
    assert result == [str(coll_a.id)]
    collections.get_schema.assert_awaited_once_with(coll_a.id)


# ── full-route authz sweep ─────────────────────────────────────────────────────────────────────
#
# The one deliberately-public /api/v1 route: it authenticates (a valid bearer is still required)
# but demands no specific capability, by design — a search-only key must still be able to ask
# "what am I" without probing endpoints and collecting 403s.
_CAPABILITY_EXEMPT_ROUTES = {("GET", "/api/v1/auth/whoami")}


def _dependency_qualnames(dependant) -> list[str]:
    """Flatten a FastAPI ``Dependant``'s dependency tree into every dependency callable's qualname."""
    names: list[str] = []
    for sub in dependant.dependencies:
        names.append(sub.call.__qualname__)
        names.extend(_dependency_qualnames(sub))
    return names


def test_every_api_v1_route_is_capability_gated(fastapi_app) -> None:
    """No `/api/v1` route may be reachable without a `require(Capability.X)` dependency.

    FastAPI's router resolves prefixes/dependencies lazily (`_IncludedRouter` +
    `fastapi.routing.iter_route_contexts`) — plain `app.routes` yields unresolved include-wrapper
    objects, not the effective path/dependant, so the sweep must go through the same helper
    `get_openapi` itself uses to flatten the route table. `/auth/whoami` is the one documented
    exception (see `_CAPABILITY_EXEMPT_ROUTES`); every other `/api/v1` route must carry
    `require(...)`'s `_authorize` dependency somewhere in its dependency tree.
    """
    from fastapi import routing  # noqa: PLC0415

    unguarded: list[str] = []
    checked = 0
    for ctx in routing.iter_route_contexts(fastapi_app.routes):
        if not isinstance(ctx.original_route, routing.APIRoute):
            continue
        path = ctx.path
        if not path or not path.startswith("/api/v1"):
            continue
        for method in sorted((ctx.methods or ()) - {"HEAD", "OPTIONS"}):
            checked += 1
            if (method, path) in _CAPABILITY_EXEMPT_ROUTES:
                continue
            names = _dependency_qualnames(ctx.dependant)
            if not any(name.endswith("require.<locals>._authorize") for name in names):
                unguarded.append(f"{method} {path}")

    # A sanity floor so a broken enumeration (e.g. a future FastAPI upgrade changing the lazy
    # routing internals) fails loudly as "found too few routes", not as a silent false-green.
    assert checked > 50, "route sweep found suspiciously few /api/v1 routes — enumeration broke"
    assert unguarded == [], f"routes with no capability gate: {unguarded}"


def test_whoami_route_is_authenticated_but_capability_free(fastapi_app) -> None:
    """The one capability-exempt route is exempt from CAPABILITY, never from authentication."""
    from fastapi import routing  # noqa: PLC0415

    for ctx in routing.iter_route_contexts(fastapi_app.routes):
        if isinstance(ctx.original_route, routing.APIRoute) and ctx.path == "/api/v1/auth/whoami":
            names = _dependency_qualnames(ctx.dependant)
            assert any(name == "authenticate" for name in names)
            assert not any(name.endswith("require.<locals>._authorize") for name in names)
            return

    pytest.fail("GET /api/v1/auth/whoami not found in the route table")

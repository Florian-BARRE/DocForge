"""Trace-payload purge routes: reclaim the stored full execution-trace payloads of a whole collection
or a single document. The scope target must exist (404 for an unknown collection/document), the purge
itself is idempotent (a scope that stored nothing returns zeros, never a 404) and best-effort (the
façade never raises). No live stack — the façade is mocked.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

COLLECTION_ID = uuid.uuid4()
DOCUMENT_ID = uuid.uuid4()

# Two stable collection ids — the "owned" (A) tenant and the "foreign" (B) tenant.
COLL_A = "11111111-1111-1111-1111-111111111111"
COLL_B = "22222222-2222-2222-2222-222222222222"


def _scoped(collection_id: str):
    """An AuthPrincipal scoped to exactly one collection (read+write, not full access)."""
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    key = SimpleNamespace(
        permissions={"capabilities": ["read", "write"], "collections": [collection_id]},
        revoked_at=None,
        user_id="user-1",
    )
    return AuthPrincipal(user=SimpleNamespace(is_active=True), key=key, is_full_access=False)


def test_purge_routes_are_registered(fastapi_app) -> None:
    paths = fastapi_app.openapi()["paths"]
    assert "post" in paths["/api/v1/collections/{collection_id}/trace-payloads/purge"]
    assert "post" in paths["/api/v1/documents/{document_id}/trace-payloads/purge"]


def test_collection_purge_returns_counts(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    monkeypatch.setattr(
        CONTEXT.database.collections,
        "get",
        AsyncMock(return_value=SimpleNamespace(id=COLLECTION_ID)),
    )
    purge = AsyncMock(return_value=(12, 24))
    monkeypatch.setattr(CONTEXT.database.trace_payloads, "purge_for_collection", purge)

    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/trace-payloads/purge")

    assert response.status_code == 200, response.text
    assert response.json() == {"purged_jobs": 12, "deleted_objects": 24}
    purge.assert_awaited_once_with(COLLECTION_ID)


def test_collection_purge_no_stored_trace_is_a_zero_no_op(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    monkeypatch.setattr(
        CONTEXT.database.collections,
        "get",
        AsyncMock(return_value=SimpleNamespace(id=COLLECTION_ID)),
    )
    monkeypatch.setattr(
        CONTEXT.database.trace_payloads, "purge_for_collection", AsyncMock(return_value=(0, 0))
    )

    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/trace-payloads/purge")

    assert response.status_code == 200, response.text
    assert response.json() == {"purged_jobs": 0, "deleted_objects": 0}


def test_collection_purge_unknown_collection_is_404(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=None))
    purge = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.trace_payloads, "purge_for_collection", purge)

    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/trace-payloads/purge")

    assert response.status_code == 404, response.text
    purge.assert_not_awaited()


def test_document_purge_returns_counts(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    monkeypatch.setattr(
        CONTEXT.database.documents,
        "get",
        AsyncMock(return_value=SimpleNamespace(id=DOCUMENT_ID, collection_id=COLLECTION_ID)),
    )
    purge = AsyncMock(return_value=(3, 6))
    monkeypatch.setattr(CONTEXT.database.trace_payloads, "purge_for_document", purge)

    response = client.post(f"/api/v1/documents/{DOCUMENT_ID}/trace-payloads/purge")

    assert response.status_code == 200, response.text
    assert response.json() == {"purged_jobs": 3, "deleted_objects": 6}
    purge.assert_awaited_once_with(DOCUMENT_ID)


def test_document_purge_unknown_document_is_404(client, monkeypatch) -> None:
    from backend.context import CONTEXT

    monkeypatch.setattr(CONTEXT.database.documents, "get", AsyncMock(return_value=None))
    purge = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.trace_payloads, "purge_for_document", purge)

    response = client.post(f"/api/v1/documents/{DOCUMENT_ID}/trace-payloads/purge")

    assert response.status_code == 404, response.text
    purge.assert_not_awaited()


# --------------------------------------------------------------------------- #
# Cross-tenant scope enforcement (the destructive routes ship WITH a scope guard)
# --------------------------------------------------------------------------- #


async def test_collection_purge_cross_tenant_is_403(fastapi_app, monkeypatch) -> None:
    """A key scoped to collection B calling A's purge is 403 — and never reaches the reclaim."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.collections.router import purge_collection_trace_payloads  # noqa: PLC0415

    monkeypatch.setattr(
        CONTEXT.database.collections,
        "get",
        AsyncMock(return_value=SimpleNamespace(id=uuid.UUID(COLL_A))),
    )
    purge = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.trace_payloads, "purge_for_collection", purge)

    with pytest.raises(HTTPException) as exc:
        await purge_collection_trace_payloads(
            collection_id=uuid.UUID(COLL_A), principal=_scoped(COLL_B)
        )

    assert exc.value.status_code == 403
    purge.assert_not_awaited()  # another tenant's payloads are never reclaimed


async def test_document_purge_cross_tenant_is_403(fastapi_app, monkeypatch) -> None:
    """A key scoped to B calling the purge of a document that lives in A is 403 — no reclaim runs."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.documents.router import purge_document_trace_payloads  # noqa: PLC0415

    monkeypatch.setattr(
        CONTEXT.database.documents,
        "get",
        AsyncMock(
            return_value=SimpleNamespace(id=uuid.UUID(COLL_A), collection_id=uuid.UUID(COLL_A))
        ),
    )
    purge = AsyncMock()
    monkeypatch.setattr(CONTEXT.database.trace_payloads, "purge_for_document", purge)

    with pytest.raises(HTTPException) as exc:
        await purge_document_trace_payloads(document_id=uuid.uuid4(), principal=_scoped(COLL_B))

    assert exc.value.status_code == 403
    purge.assert_not_awaited()


# --------------------------------------------------------------------------- #
# Capability gate — both destructive routes demand Capability.WRITE
# --------------------------------------------------------------------------- #


def _authorize_capabilities(dependant) -> list:
    """Collect the ``capability`` captured by every ``require(...)._authorize`` in a dependant tree."""
    from backend.libs.auth.permissions import Capability  # noqa: PLC0415

    found: list[Capability] = []
    for sub in dependant.dependencies:
        if sub.call.__qualname__.endswith("require.<locals>._authorize") and sub.call.__closure__:
            found.extend(
                cell.cell_contents
                for cell in sub.call.__closure__
                if isinstance(cell.cell_contents, Capability)
            )
        found.extend(_authorize_capabilities(sub))
    return found


def test_purge_routes_require_write_capability(fastapi_app) -> None:
    """Both purge routes are gated by ``require(Capability.WRITE)`` (the guard is actually wired)."""
    from fastapi import routing  # noqa: PLC0415

    from backend.libs.auth.permissions import Capability  # noqa: PLC0415

    targets = {
        "/api/v1/collections/{collection_id}/trace-payloads/purge",
        "/api/v1/documents/{document_id}/trace-payloads/purge",
    }
    seen: set[str] = set()
    for ctx in routing.iter_route_contexts(fastapi_app.routes):
        if not isinstance(ctx.original_route, routing.APIRoute) or ctx.path not in targets:
            continue
        seen.add(ctx.path)
        assert Capability.WRITE in _authorize_capabilities(ctx.dependant), ctx.path

    assert seen == targets, f"purge routes not found in the route table: {targets - seen}"

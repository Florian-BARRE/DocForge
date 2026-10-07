"""The read_text / read_technical capability split (finding L4): every read route's declared
capability is pinned (a parametric matrix walking the REAL app's routes), each technical route denies
a read_text-only key and admits a read_technical one, every text route admits read_text, a legacy
`read` key keeps the whole read surface, and no route still demands the legacy alias. The HTTP-level
checks run the real app with auth ON and an `agent_reader` key; `get_collection` withholds the blobs
and the chunks route drops geometry for a non-technical reader.

``from backend...`` imports are deferred until the ``fastapi_app`` fixture registered app/ on sys.path.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

COLL = "11111111-1111-1111-1111-111111111111"
_G3_PENDING = "/config-versions"

TEXT_ROUTES = {
    ("GET", "/collection-aliases"),
    ("GET", "/collections"),
    ("GET", "/collections/{collection_id}"),
    ("GET", "/collections/{collection_id}/describe"),
    ("GET", "/collections/{collection_id}/documents"),
    ("POST", "/collections/{collection_id}/documents/query"),
    ("POST", "/collections/{collection_id}/chunks/browse"),
    ("GET", "/documents/{document_id}"),
    ("GET", "/documents/{document_id}/markdown"),
    ("GET", "/documents/{document_id}/html"),
    ("GET", "/documents/{document_id}/chunks"),
    ("GET", "/documents/{document_id}/outline"),
    ("GET", "/chunks/{chunk_id}/context"),
    ("GET", "/jobs"),
    ("GET", "/jobs/{job_id}"),
}

TECHNICAL_ROUTES = {
    ("GET", "/pipelines"),
    ("GET", "/pipelines/{key}"),
    ("POST", "/pipelines/{key}/inspect"),
    ("POST", "/pipelines/{key}/edit"),
    ("POST", "/pipelines/{key}/stages/view"),
    ("POST", "/pipelines/{key}/stages/apply"),
    ("GET", "/collections/contract-schema"),
    ("GET", "/collections/{collection_id}/health"),
    ("GET", "/collections/{collection_id}/storage"),
    ("POST", "/collections/{collection_id}/estimate"),
    ("GET", "/jobs/stage-durations"),
    ("GET", "/jobs/cost"),
    ("GET", "/jobs/workers/live"),
    ("GET", "/jobs/queue"),
    ("GET", "/jobs/failures/breakdown"),
    ("GET", "/jobs/failures/new"),
    ("GET", "/jobs/timeseries"),
    ("GET", "/jobs/{job_id}/events"),
    ("GET", "/jobs/{job_id}/events/{event_id}/payload"),
    ("GET", "/jobs/{job_id}/stream"),
    ("POST", "/collections/{collection_id}/export"),
    ("GET", "/transfers/{transfer_id}"),
    ("GET", "/transfers/{transfer_id}/download"),
    ("GET", "/collections/{collection_id}/snippets/{kind}"),
    ("GET", "/documents/{document_id}/pages"),
    ("GET", "/documents/{document_id}/ir"),
    ("GET", "/documents/{document_id}/provenance"),
    ("GET", "/blobs/{content_hash}"),
    ("GET", "/search/health"),
    ("GET", "/audit"),
}

# Write routes whose RESPONSE is inherently technical (a pipeline stage view, a dry-run IR summary +
# trace): they demand write AND read_technical (finding M2).
WRITE_TECHNICAL_ROUTES = {
    ("POST", "/collections/{collection_id}/pipeline/stages/apply"),
    ("POST", "/collections/{collection_id}/pipeline/preview"),
    ("POST", "/collections/{collection_id}/pipeline/preview/jobs"),
    ("GET", "/collections/{collection_id}/pipeline/preview/jobs/{preview_id}"),
}


# ── route introspection ──────────────────────────────────────────────────────────────────────────


def _capabilities(dependant) -> list:
    """Collect every Capability captured by a `require(...)` closure in a dependant tree."""
    found = []
    for dependency in dependant.dependencies:
        for cell in getattr(dependency.call, "__closure__", None) or ():
            value = cell.cell_contents
            if type(value).__name__ == "Capability":
                found.append(value)
        found.extend(_capabilities(dependency))
    return found


def _route_capabilities(app) -> dict:
    """Map (method, router-local path) → the set of capability values its guards demand."""
    from fastapi.routing import APIRoute  # noqa: PLC0415

    table: dict = {}

    def walk(routes) -> None:
        for route in routes:
            if isinstance(route, APIRoute):
                for method in route.methods:
                    table[(method, route.path)] = {c.value for c in _capabilities(route.dependant)}
            elif hasattr(route, "original_router"):
                walk(route.original_router.routes)

    walk(app.routes)
    # The config-history routes are owned by the concurrent wave G3, which classifies them itself;
    # drop this exemption once they declare read_text / read_technical.
    return {route: caps for route, caps in table.items() if _G3_PENDING not in route[1]}


def _principal(capabilities):
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    key = SimpleNamespace(
        permissions={"capabilities": capabilities, "collections": ["*"]},
        revoked_at=None,
        user_id="u",
    )
    return AuthPrincipal(user=SimpleNamespace(is_active=True), key=key, is_full_access=False)


def _request() -> Request:
    return Request({"type": "http", "path_params": {"collection_id": COLL}, "headers": []})


# ── the declared matrix ──────────────────────────────────────────────────────────────────────────


def test_no_route_demands_the_legacy_read_alias(fastapi_app) -> None:
    table = _route_capabilities(fastapi_app)
    assert not [route for route, caps in table.items() if "read" in caps]


def test_every_read_route_is_classified(fastapi_app) -> None:
    table = _route_capabilities(fastapi_app)
    text = {route for route, caps in table.items() if "read_text" in caps}
    technical = {route for route, caps in table.items() if "read_technical" in caps}
    # A new read route must be consciously placed on one side (update the sets above).
    assert text == TEXT_ROUTES
    assert technical == TECHNICAL_ROUTES | WRITE_TECHNICAL_ROUTES


def test_technical_write_routes_demand_both(fastapi_app) -> None:
    table = _route_capabilities(fastapi_app)
    for route in WRITE_TECHNICAL_ROUTES:
        assert table[route] == {"write", "read_technical"}, route


@pytest.mark.parametrize("route", sorted(TECHNICAL_ROUTES))
def test_technical_route_denies_read_text_and_admits_read_technical(fastapi_app, route) -> None:
    from backend.libs.auth import AuthzGuard, Capability  # noqa: PLC0415

    [capability] = _route_capabilities(fastapi_app)[route]
    with pytest.raises(HTTPException) as exc:
        AuthzGuard.enforce(Capability(capability), _principal(["read_text", "search"]), _request())
    assert exc.value.status_code == 403
    AuthzGuard.enforce(Capability(capability), _principal(["read_technical"]), _request())
    AuthzGuard.enforce(Capability(capability), _principal(["read"]), _request())


@pytest.mark.parametrize("route", sorted(TEXT_ROUTES))
def test_text_route_admits_read_text_and_legacy_read(fastapi_app, route) -> None:
    from backend.libs.auth import AuthzGuard, Capability  # noqa: PLC0415

    [capability] = _route_capabilities(fastapi_app)[route]
    AuthzGuard.enforce(Capability(capability), _principal(["read_text"]), _request())
    AuthzGuard.enforce(Capability(capability), _principal(["read"]), _request())


# ── HTTP: an agent_reader key against the real app ───────────────────────────────────────────────


def _agent_reader_resolves(monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    key = SimpleNamespace(
        id=uuid.uuid4(),
        permissions={"capabilities": ["read_text", "search"], "collections": ["*"]},
        revoked_at=None,
        user_id=uuid.uuid4(),
        expires_at=None,
        last_used_at=None,
    )
    auth = CONTEXT.database.auth
    monkeypatch.setattr(
        auth, "get_key_with_user", AsyncMock(return_value=(key, SimpleNamespace(is_active=True)))
    )
    monkeypatch.setattr(auth, "touch_key_last_used", AsyncMock())
    from backend.libs.auth.dependency import _KEY_CACHE  # noqa: PLC0415

    monkeypatch.setattr(_KEY_CACHE, "get", lambda _hash: (False, None))


def test_agent_reader_gets_403_on_provenance_and_passes_authz_on_markdown(
    client, monkeypatch
) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415

    _agent_reader_resolves(monkeypatch)
    monkeypatch.setattr(CONTEXT.database.documents, "get", AsyncMock(return_value=None))
    headers = {"Authorization": "Bearer df_agent"}
    doc = uuid.uuid4()

    assert client.get(f"/api/v1/documents/{doc}/provenance", headers=headers).status_code == 403
    # Authorized: the handler runs and reports the (mocked) unknown document.
    assert client.get(f"/api/v1/documents/{doc}/markdown", headers=headers).status_code == 404


# ── payload shaping for a non-technical reader ───────────────────────────────────────────────────


async def test_get_collection_withholds_blobs_from_read_text(fastapi_app, monkeypatch) -> None:
    import importlib  # noqa: PLC0415

    from backend.context import CONTEXT  # noqa: PLC0415

    module = importlib.import_module("backend.routers.collections.router")
    from backend.routers.collections.models import CollectionModel  # noqa: PLC0415

    model = CollectionModel.model_construct(name="c", pipeline={"nodes": []}, search={"x": 1})
    database = SimpleNamespace(
        collections=SimpleNamespace(get=AsyncMock(return_value=object()), get_schema=AsyncMock()),
        collection_aliases=SimpleNamespace(
            names_for=AsyncMock(return_value=[]), name_is_alias=AsyncMock(return_value=False)
        ),
        index_state=SimpleNamespace(missing=AsyncMock(return_value=[])),
    )
    monkeypatch.setattr(CONTEXT, "database", database)
    monkeypatch.setattr(module.CollectionHelpers, "to_model", lambda *_a, **_k: model)

    lean = await module.get_collection(uuid.UUID(COLL), principal=_principal(["read_text"]))
    full = await module.get_collection(uuid.UUID(COLL), principal=_principal(["read"]))

    assert lean.pipeline is None and lean.search is None and lean.name == "c"
    assert full.pipeline == {"nodes": []} and full.search == {"x": 1}


async def test_chunks_force_lean_shape_for_read_text(fastapi_app, monkeypatch) -> None:
    from fastapi import Response  # noqa: PLC0415

    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.explorer.router import get_document_chunks  # noqa: PLC0415

    document = SimpleNamespace(id=uuid.uuid4(), collection_id=uuid.UUID(COLL))
    documents = SimpleNamespace(
        get=AsyncMock(return_value=document),
        get_chunks=AsyncMock(return_value=[]),
        get_document_chunk_composition=AsyncMock(return_value=[]),
        get_document_chunk_metadata=AsyncMock(return_value=[]),
        get_block_locations_for_chunks=AsyncMock(return_value={}),
    )
    collections = SimpleNamespace(get_schema=AsyncMock(return_value=[]))
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(documents=documents, collections=collections)
    )

    await get_document_chunks(
        document.id, Response(), limit=None, offset=0, include_geometry=True,
        principal=_principal(["read_text"]),
    )  # fmt: skip

    documents.get_document_chunk_composition.assert_not_called()

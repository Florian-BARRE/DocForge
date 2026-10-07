"""The read_technical surface withheld from text-only callers (findings M1, M2, L1, L3).

M1: the search + chunk-browse hits never carry the drawing geometry (block_ids, 0-based page, bbox,
block_locations) for a key without read_technical, even when ``return_fields`` asks for it —
page_number (the citation) stays; a technical key still gets it. M2: every route returning a
collection contract either shapes it through CollectionTechnicalView or demands read_technical (a
source-level ratchet over the real app), and the shape nulls the blobs on the PATCH response too. L1:
a job's error has its URLs / host:port / request paths masked for a non-technical reader (list, get,
document failure_reason) while error_type and the failed node are kept. L3: key creation/rotation
refuses the reserved author names "root" / "anonymous".

``from backend...`` imports are deferred until the ``fastapi_app`` fixture registered app/ on sys.path.
"""

import inspect
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from shared_libs.public_models import FieldType
from shared_libs.public_models.search import Hit, SearchResult

COLL = "33333333-3333-3333-3333-333333333333"
_TECHNICAL_GEOMETRY = {"block_ids", "page", "bbox", "block_locations"}
_PROVIDER_ERROR = (
    "ConnectError: Client error '502 Bad Gateway' for url 'http://bge_server:8000/embed?x=1' "
    "(HTTPConnectionPool(host='paddle_server', port=8080): Max retries exceeded with url: /ocr) "
    "peer 10.0.3.7:9000/v1 also failed via ollama.internal:11434/api"
)


# ── helpers ──────────────────────────────────────────────────────────────────────────────────────


def _key_resolves(monkeypatch, capabilities: list[str]) -> None:
    """Turn auth ON and make every bearer resolve to a wildcard key holding ``capabilities``."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.auth.dependency import _KEY_CACHE  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", True)
    key = SimpleNamespace(
        id=uuid.uuid4(),
        name="k",
        prefix="df_k",
        permissions={"capabilities": capabilities, "collections": ["*"]},
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
    monkeypatch.setattr(_KEY_CACHE, "get", lambda _hash: (False, None))


def _principal(capabilities: list[str] | None):
    """A scoped principal (None = full access)."""
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    key = SimpleNamespace(
        id=uuid.uuid4(),
        name="k",
        prefix="df_k",
        permissions=None
        if capabilities is None
        else {"capabilities": capabilities, "collections": ["*"]},
        revoked_at=None,
        user_id="u",
    )
    return AuthPrincipal(
        user=SimpleNamespace(is_active=True), key=key, is_full_access=capabilities is None
    )


def _hit(chunk: int) -> Hit:
    """A hydrated hit carrying the full geometry in its bag (as the read port emits it)."""
    return Hit(
        chunk_id=f"11111111-1111-1111-1111-{chunk:012d}",
        document_id="doc-a",
        score=0.9,
        rank=chunk,
        text=f"chunk {chunk}",
        metadata={
            "chunk_index": chunk,
            "token_count": 9,
            "heading_path": ["H"],
            "filename": "f.pdf",
            "document_title": "T",
            "document_metadata": {"topic": "a"},
            "block_ids": ["b"],
            "page": 2,
            "bbox": [0.1, 0.1, 0.2, 0.2],
            "block_locations": [{"page": 2, "bbox": [0.1, 0.1, 0.2, 0.2]}],
        },
    )


def _wire_reads(monkeypatch) -> None:
    """Patch the collection reads + make the stored-value filter resolution a pass-through."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.search import FilterResolution, SearchFilterResolver  # noqa: PLC0415

    pipeline = {
        "node_type": "group",
        "id": "root",
        "nodes": [
            {
                "node_type": "action",
                "id": "embed",
                "family": "embed",
                "kind": "bge_server",
                "config": {"model": "BAAI/bge-m3", "base_url": "http://bge:8008"},
            }
        ],
        "transitions": [],
        "bindings": {},
    }
    collection = SimpleNamespace(pipeline=pipeline, search={}, title_field=None)
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    schema = [
        SimpleNamespace(
            field_name="topic", filterable=True, field_type=FieldType.STRING, enum_values=None
        )
    ]
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=schema))

    async def _resolve(self, filters, schema, sent=None):
        return FilterResolution(filters=dict(filters or {}), original=dict(sent or {}))

    monkeypatch.setattr(SearchFilterResolver, "resolve", _resolve)


def _wire_search(monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415

    _wire_reads(monkeypatch)
    result = SearchResult(query="q", hits=[_hit(1)])
    monkeypatch.setattr(
        CONTEXT.search_service, "search", AsyncMock(return_value=(result, (0, 0, None, 0)))
    )


def _wire_browse(monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.search import BrowsePage  # noqa: PLC0415

    _wire_reads(monkeypatch)
    browse = AsyncMock(return_value=BrowsePage(hits=[_hit(1)], next_cursor=None))
    monkeypatch.setattr(CONTEXT, "chunk_browser", SimpleNamespace(browse=browse), raising=False)


_GEOMETRY_ASK = ["text", "page_number", *sorted(_TECHNICAL_GEOMETRY)]
_BEARER = {"Authorization": "Bearer df_test"}


# ── M1: geometry ─────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("return_fields", [None, _GEOMETRY_ASK])
def test_search_withholds_geometry_from_a_text_reader(client, monkeypatch, return_fields) -> None:
    _key_resolves(monkeypatch, ["read_text", "search"])
    _wire_search(monkeypatch)
    body = {"query": "q", "limit": 1}
    if return_fields is not None:
        body["return_fields"] = return_fields

    response = client.post(f"/api/v1/collections/{COLL}/search", json=body, headers=_BEARER)

    assert response.status_code == 200, response.text
    [hit] = response.json()["hits"]
    assert _TECHNICAL_GEOMETRY.isdisjoint(hit)
    assert hit["page_number"] == 3 and hit["text"] == "chunk 1"


def test_search_serves_geometry_to_a_technical_reader(client, monkeypatch) -> None:
    _key_resolves(monkeypatch, ["read_text", "read_technical", "search"])
    _wire_search(monkeypatch)

    response = client.post(
        f"/api/v1/collections/{COLL}/search", json={"query": "q", "limit": 1}, headers=_BEARER
    )

    assert response.status_code == 200, response.text
    [hit] = response.json()["hits"]
    assert _TECHNICAL_GEOMETRY <= set(hit)


@pytest.mark.parametrize(
    ("capabilities", "expect_geometry"),
    [(["read_text"], False), (["read_text", "read_technical"], True)],
)
def test_browse_geometry_follows_read_technical(
    client, monkeypatch, capabilities, expect_geometry
) -> None:
    _key_resolves(monkeypatch, capabilities)
    _wire_browse(monkeypatch)

    response = client.post(
        f"/api/v1/collections/{COLL}/chunks/browse",
        json={"return_fields": _GEOMETRY_ASK},
        headers=_BEARER,
    )

    assert response.status_code == 200, response.text
    [chunk] = response.json()["chunks"]
    assert (_TECHNICAL_GEOMETRY <= set(chunk)) is expect_geometry
    assert _TECHNICAL_GEOMETRY.isdisjoint(chunk) is not expect_geometry
    assert chunk["page_number"] == 3


# ── M2: collection contracts ─────────────────────────────────────────────────────────────────────


def test_every_collection_returning_route_is_shaped_or_technical(fastapi_app) -> None:
    """A route answering a CollectionModel either shapes it or demands read_technical."""
    from fastapi.routing import APIRoute  # noqa: PLC0415

    from backend.routers.collections.models import CollectionModel  # noqa: PLC0415

    def _caps(dependant) -> set[str]:
        found: set[str] = set()
        for dependency in dependant.dependencies:
            for cell in getattr(dependency.call, "__closure__", None) or ():
                if type(cell.cell_contents).__name__ == "Capability":
                    found.add(cell.cell_contents.value)
            found |= _caps(dependency)
        return found

    def _walk(routes) -> list:
        found = []
        for route in routes:
            if isinstance(route, APIRoute):
                found.append(route)
            elif hasattr(route, "original_router"):
                found.extend(_walk(route.original_router.routes))
        return found

    unshaped = []
    checked = 0
    for route in _walk(fastapi_app.routes):
        model = route.response_model
        inner = getattr(model, "__args__", (model,))[0]
        if not (inspect.isclass(inner) and issubclass(inner, CollectionModel)):
            continue
        checked += 1
        source = inspect.getsource(inspect.unwrap(route.endpoint))
        if "CollectionTechnicalView.shape" not in source and "read_technical" not in _caps(
            route.dependant
        ):
            unshaped.append(f"{sorted(route.methods)} {route.path}")

    assert checked >= 4  # list, get, create, patch
    assert unshaped == []


def test_shape_nulls_blobs_on_the_patch_response_and_keeps_the_diff(fastapi_app) -> None:
    from backend.routers.collections.models import UpdateCollectionResponse  # noqa: PLC0415
    from backend.routers.collections.technical_view import CollectionTechnicalView  # noqa: PLC0415

    response = UpdateCollectionResponse.model_construct(
        name="c", pipeline={"nodes": []}, search={"x": 1}, dry_run=True, schema_diff={"added": []}
    )

    [lean] = CollectionTechnicalView.shape([response], _principal(["write"]))
    [full] = CollectionTechnicalView.shape([response], _principal(["write", "read_technical"]))

    assert lean.pipeline is None and lean.search is None
    assert lean.dry_run is True and lean.schema_diff == {"added": []}
    assert full is response


# ── L1: job error ────────────────────────────────────────────────────────────────────────────────


def test_mask_strips_every_network_locator_and_keeps_the_message(fastapi_app) -> None:
    from backend.libs.error_redaction import JobErrorRedactor  # noqa: PLC0415

    masked = JobErrorRedactor.mask(_PROVIDER_ERROR)

    for leak in ("bge_server", "8000", "/embed", "paddle_server", "8080", "/ocr", "10.0.3.7"):
        assert leak not in masked, leak
    assert "ollama.internal" not in masked and "11434" not in masked
    assert masked.startswith("ConnectError: Client error '502 Bad Gateway'")
    assert "Max retries exceeded" in masked
    # A timestamp-like token is not a host:port.
    assert JobErrorRedactor.mask("TimeoutError: at 12:30 after 30s") == (
        "TimeoutError: at 12:30 after 30s"
    )


def _failed_job():
    from shared_libs.services.db.postgresql.tables import JobKind, JobStatus  # noqa: PLC0415

    return SimpleNamespace(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        collection_id=uuid.UUID(COLL),
        status=JobStatus.FAILED,
        kind=JobKind.INGEST,
        cancel_requested=False,
        progress=40,
        current_stage="embed",
        error=_PROVIDER_ERROR,
        attempt=1,
        started_at=None,
        finished_at=None,
        updated_at=datetime(2026, 10, 1, tzinfo=UTC),
        total_prompt_tokens=0,
        total_completion_tokens=0,
        cost_usd=0,
        items_done=None,
        items_total=None,
        failed_node_id="embed",
        failed_node_kind="bge_server",
        failed_item_index=None,
        error_type="ConnectError",
    )


def _entry(job):
    return SimpleNamespace(
        job=job,
        document_filename="f.pdf",
        document_title=None,
        collection_name="c",
        document_display_title=None,
    )


@pytest.mark.parametrize(
    ("capabilities", "masked"),
    [(["read_text"], True), (["read_technical"], False), (None, False)],
)
async def test_job_routes_mask_the_error_without_read_technical(
    fastapi_app, monkeypatch, capabilities, masked
) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.jobs.router import get_job, list_jobs  # noqa: PLC0415

    entry = _entry(_failed_job())
    jobs = SimpleNamespace(
        get_with_names=AsyncMock(return_value=entry),
        list_jobs_with_names=AsyncMock(return_value=[entry]),
        count_jobs=AsyncMock(return_value=1),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs), raising=False)
    principal = _principal(capabilities)

    single = await get_job(job_id=entry.job.id, principal=principal)
    page = await list_jobs(
        collection_id=uuid.UUID(COLL),
        status=None,
        stage=None,
        error_type=None,
        search=None,
        created_after=None,
        created_before=None,
        sort="created",
        order="newest",
        limit=10,
        offset=0,
        principal=principal,
    )

    for status in (single, page.jobs[0]):
        assert ("bge_server" not in status.error) is masked
        assert status.error_type == "ConnectError"
        assert status.failed_node_id == "embed" and status.failed_node_kind == "bge_server"
        assert status.current_stage == "embed"


async def test_document_failure_reason_is_masked_for_a_text_reader(
    fastapi_app, monkeypatch
) -> None:
    import importlib  # noqa: PLC0415

    from backend.context import CONTEXT  # noqa: PLC0415
    from shared_libs.services.db.postgresql.tables import DocumentStatus  # noqa: PLC0415

    module = importlib.import_module("backend.routers.explorer.router")
    jobs = SimpleNamespace(get_latest_for_document=AsyncMock(return_value=_failed_job()))
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(jobs=jobs), raising=False)
    document = SimpleNamespace(id=uuid.uuid4(), status=DocumentStatus.FAILED)

    lean = await module._failure_reason(document, _principal(["read_text"]))
    full = await module._failure_reason(document, _principal(["read_technical"]))

    assert "bge_server" not in lean and lean.startswith("ConnectError")
    assert full == _PROVIDER_ERROR


# ── L3: reserved key names ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["root", "anonymous", " Root ", "ANONYMOUS"])
def test_key_create_and_rotate_refuse_reserved_names(fastapi_app, name) -> None:
    from backend.routers.auth.models import CreateKeyRequest, RotateKeyRequest  # noqa: PLC0415

    with pytest.raises(ValidationError, match="reserved"):
        CreateKeyRequest(name=name)
    with pytest.raises(ValidationError, match="reserved"):
        RotateKeyRequest(name=name)


def test_key_create_route_answers_422_on_a_reserved_name(client) -> None:
    response = client.post("/api/v1/auth/keys", json={"name": "root"})
    assert response.status_code == 422
    assert "reserved" in response.text


def test_regular_key_name_is_accepted(fastapi_app) -> None:
    from backend.routers.auth.models import CreateKeyRequest  # noqa: PLC0415

    assert CreateKeyRequest(name="root-ci").name == "root-ci"

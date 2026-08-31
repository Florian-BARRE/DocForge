"""Corpus grid query route: POST /collections/{id}/documents/query. Registration + the fail-fast
order (404 unknown collection, 422 bad metadata field/operator/sort) BEFORE any page read, the
page-size clamp, and the row shaping (base fields + a compact metadata map, bulk-loaded — no N+1).
No live stack — the Database façade + schema are mocked.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

COLLECTION_ID = uuid.uuid4()


def _field(field_id: int, name: str, ftype: str, *, filterable: bool = True) -> SimpleNamespace:
    """A stand-in MetadataField row (only the attributes the mapper reads)."""
    return SimpleNamespace(id=field_id, field_name=name, field_type=ftype, filterable=filterable)


def _document(**overrides) -> SimpleNamespace:
    """A stand-in Document row carrying every field the grid row maps."""
    base = dict(
        id=uuid.uuid4(),
        filename="report.pdf",
        format="pdf",
        status="done",
        page_count=12,
        file_size=2048,
        created_at=None,
        title="Q3 report",
        language="en",
        enabled=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _wire(monkeypatch, *, collection, schema, documents=(), total=0, metadata=None):
    """Point CONTEXT.database at mocked collections + documents façades."""
    from backend.context import CONTEXT

    collections = SimpleNamespace(
        get=AsyncMock(return_value=collection),
        get_schema=AsyncMock(return_value=list(schema)),
    )
    documents_facade = SimpleNamespace(
        query=AsyncMock(return_value=(list(documents), total)),
        get_metadata_for_documents=AsyncMock(return_value=metadata or {}),
    )
    monkeypatch.setattr(
        CONTEXT, "database", SimpleNamespace(collections=collections, documents=documents_facade)
    )
    return collections, documents_facade


def test_query_route_is_registered(fastapi_app) -> None:
    paths = fastapi_app.openapi()["paths"]
    assert "post" in paths["/api/v1/collections/{collection_id}/documents/query"]


def test_query_unknown_collection_is_404(client, monkeypatch) -> None:
    _wire(monkeypatch, collection=None, schema=[])
    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/documents/query", json={})
    assert response.status_code == 404


def test_query_unknown_metadata_field_is_422(client, monkeypatch) -> None:
    _wire(monkeypatch, collection=SimpleNamespace(id=COLLECTION_ID), schema=[])
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/query",
        json={"filter": {"metadata": [{"field": "ghost", "op": "eq", "value": 1}]}},
    )
    assert response.status_code == 422
    assert "ghost" in response.json()["detail"]


def test_query_non_filterable_metadata_field_is_422(client, monkeypatch) -> None:
    schema = [_field(1, "notes", "text", filterable=False)]
    _wire(monkeypatch, collection=SimpleNamespace(id=COLLECTION_ID), schema=schema)
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/query",
        json={"filter": {"metadata": [{"field": "notes", "op": "contains", "value": "x"}]}},
    )
    assert response.status_code == 422
    assert "not filterable" in response.json()["detail"]


def test_query_bad_operator_for_type_is_422(client, monkeypatch) -> None:
    schema = [_field(1, "year", "integer")]
    _wire(monkeypatch, collection=SimpleNamespace(id=COLLECTION_ID), schema=schema)
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/query",
        json={"filter": {"metadata": [{"field": "year", "op": "contains", "value": "2"}]}},
    )
    assert response.status_code == 422
    assert "invalid for field" in response.json()["detail"]


def test_query_unknown_sort_field_is_422(client, monkeypatch) -> None:
    _wire(monkeypatch, collection=SimpleNamespace(id=COLLECTION_ID), schema=[])
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/query",
        json={"sort": {"field": "nope", "direction": "asc"}},
    )
    assert response.status_code == 422
    assert "Unknown sort field" in response.json()["detail"]


def test_query_page_size_is_clamped_to_ceiling(client, monkeypatch) -> None:
    from config import RUNTIME_CONFIG

    monkeypatch.setattr(RUNTIME_CONFIG, "CORPUS_MAX_PAGE_SIZE", 50)
    _, documents_facade = _wire(
        monkeypatch, collection=SimpleNamespace(id=COLLECTION_ID), schema=[], documents=[], total=0
    )
    response = client.post(
        f"/api/v1/collections/{COLLECTION_ID}/documents/query",
        json={"pagination": {"limit": 5000, "offset": 10}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["limit"] == 50 and body["offset"] == 10
    # The clamped limit is what actually reached the façade.
    assert documents_facade.query.await_args.args[2] == 50


def test_query_shapes_rows_with_metadata_map(client, monkeypatch) -> None:
    schema = [_field(1, "author", "string"), _field(2, "year", "integer")]
    doc = _document()
    metadata = {
        doc.id: [
            SimpleNamespace(field_id=1, value="Ada", origin="user"),
            SimpleNamespace(field_id=2, value=2024, origin="user"),
        ]
    }
    _wire(
        monkeypatch,
        collection=SimpleNamespace(id=COLLECTION_ID),
        schema=schema,
        documents=[doc],
        total=1,
        metadata=metadata,
    )
    response = client.post(f"/api/v1/collections/{COLLECTION_ID}/documents/query", json={})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    row = body["rows"][0]
    assert row["filename"] == "report.pdf"
    assert row["metadata"] == {"author": "Ada", "year": 2024}

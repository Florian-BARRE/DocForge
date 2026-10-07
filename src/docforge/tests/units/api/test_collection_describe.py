"""GET /collections/{id}/describe — the lean agent guide to querying one collection.

Pins: field descriptions + real example values flow through; free text (text/text_list) never gets
examples (a note instead) and long values are truncated; non-filterable high-cardinality fields get
no examples; ``searchable_targets`` = content (both axes) + each vector-indexed field on its own axes;
example requests use the collection's real field names/values (JSON-typed); unknown collection → 404;
the route is READ-gated and collection-scoped (a key scoped elsewhere → 403); no blob leaks.

Store access is mocked via CONTEXT.database; ``from backend...`` imports are deferred until the
``fastapi_app`` fixture has registered app/ on sys.path.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from shared_libs.public_models import FieldOrigin, FieldScope, FieldType
from shared_libs.services.db.postgresql.tables import MetadataField

COLLECTION_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
LONG_VALUE = "x" * 200


def _field(name, field_type, *, filterable=False, semantic=False, lexical=False, description=None):
    """A transient metadata_field row (document scope, user origin)."""
    return MetadataField(
        id=hash(name) % 10_000,
        field_name=name,
        field_type=field_type,
        required=False,
        filterable=filterable,
        lexical=lexical,
        semantic=semantic,
        enum_values=None,
        origin=FieldOrigin.USER,
        scope=FieldScope.DOCUMENT,
        description=description,
    )


SCHEMA = [
    _field("topic", FieldType.STRING, filterable=True, semantic=True, description="Main topic."),
    _field("year", FieldType.INTEGER, filterable=True),
    _field("summary", FieldType.TEXT, filterable=True, lexical=True),
    _field("note", FieldType.STRING),
]
VALUES = {
    "topic": ["Insurance", "Banking", LONG_VALUE],
    "year": ["2024", "2023"],
    "summary": ["a long paragraph"],
    "note": ["n1"],
}
COUNTS = {"topic": 3, "year": 2, "summary": 900, "note": 500}


def _wire(monkeypatch, *, collection, schema=SCHEMA):
    """Mock CONTEXT.database with collections/documents/metadata_values seams."""
    from backend.context import CONTEXT  # noqa: PLC0415

    resolver = SimpleNamespace(
        distinct_count=AsyncMock(side_effect=lambda f: COUNTS[f.field_name]),
        distinct_values=AsyncMock(side_effect=lambda f, limit: VALUES[f.field_name][:limit]),
    )
    database = SimpleNamespace(
        collections=SimpleNamespace(
            get=AsyncMock(return_value=collection), get_schema=AsyncMock(return_value=schema)
        ),
        documents=SimpleNamespace(count_for_collection=AsyncMock(return_value=42)),
        metadata_values=resolver,
    )
    monkeypatch.setattr(CONTEXT, "database", database)
    return resolver


def _collection():
    return SimpleNamespace(
        id=COLLECTION_ID,
        name="regulatory",
        title_field="topic",
        pipeline={"secret": "sk-live"},
        search={"secret": "sk-live"},
    )


@pytest.fixture
def described(fastapi_app, monkeypatch, client):
    """GET the guide of the standard fake collection and return (json, resolver)."""
    resolver = _wire(monkeypatch, collection=_collection())
    response = client.get(f"/api/v1/collections/{COLLECTION_ID}/describe")
    assert response.status_code == 200, response.text
    return response.json(), resolver


def test_identity_and_page_note(described) -> None:
    body, _ = described
    assert body["collection_id"] == str(COLLECTION_ID)
    assert body["name"] == "regulatory"
    assert body["document_count"] == 42
    assert body["title_field"] == "topic"
    assert "page_number" in body["page_numbering"] and "1-based" in body["page_numbering"]


def test_fields_carry_description_and_truncated_examples(described) -> None:
    body, _ = described
    topic = next(f for f in body["fields"] if f["name"] == "topic")
    assert topic["description"] == "Main topic."
    assert topic["type"] == "string"
    assert topic["distinct_count"] == 3
    assert topic["example_values"][:2] == ["Insurance", "Banking"]
    assert len(topic["example_values"][2]) == 80 and topic["example_values"][2].endswith("…")


def test_text_field_gets_no_examples_but_a_note(described) -> None:
    body, resolver = described
    summary = next(f for f in body["fields"] if f["name"] == "summary")
    assert summary["example_values"] == []
    assert summary["note"] and "Free text" in summary["note"]
    sampled = [call.args[0].field_name for call in resolver.distinct_values.await_args_list]
    assert "summary" not in sampled


def test_high_cardinality_non_filterable_field_gets_no_examples(described) -> None:
    body, _ = described
    note = next(f for f in body["fields"] if f["name"] == "note")
    assert note["example_values"] == [] and note["note"] is None


def test_searchable_targets(described) -> None:
    body, _ = described
    assert body["searchable_targets"] == [
        {"field": "content", "semantic": True, "lexical": True},
        {"field": "topic", "semantic": True, "lexical": False},
        {"field": "summary", "semantic": False, "lexical": True},
    ]


def test_example_requests_use_real_fields_and_values(described) -> None:
    body, _ = described
    examples = body["example_requests"]
    assert 2 <= len(examples) <= 4
    assert examples[0] == {"query": "your question here", "limit": 5}
    assert examples[1]["filters"] == {"topic": "Insurance"}
    assert examples[2]["search_in"][1] == {"field": "topic", "semantic": True, "lexical": False}
    # The range example is JSON-typed (an int, not the stored "2024" text).
    assert examples[3]["filters"] == {"year": {"gte": 2024}}


def test_no_blob_or_secret_leaks(described) -> None:
    body, _ = described
    assert "pipeline" not in body and "search" not in body
    assert "sk-live" not in str(body)


def test_minimal_schema_still_yields_a_content_example(fastapi_app, monkeypatch, client) -> None:
    _wire(monkeypatch, collection=_collection(), schema=[])
    body = client.get(f"/api/v1/collections/{COLLECTION_ID}/describe").json()
    assert body["fields"] == []
    assert body["searchable_targets"] == [{"field": "content", "semantic": True, "lexical": True}]
    assert body["example_requests"] == [{"query": "your question here", "limit": 5}]


def test_unknown_collection_is_404(fastapi_app, monkeypatch, client) -> None:
    _wire(monkeypatch, collection=None)
    response = client.get(f"/api/v1/collections/{uuid.uuid4()}/describe")
    assert response.status_code == 404


def _route_authorizer(fastapi_app):
    """The require(...) dependency wired on the describe route (via the lazy route-table flattener)."""
    from fastapi import routing  # noqa: PLC0415

    for ctx in routing.iter_route_contexts(fastapi_app.routes):
        if ctx.path == "/api/v1/collections/{collection_id}/describe":
            return next(
                sub.call
                for sub in ctx.dependant.dependencies
                if sub.call.__qualname__.endswith("require.<locals>._authorize")
            )
    pytest.fail("describe route not found in the route table")


def _principal(permissions):
    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    key = SimpleNamespace(permissions=permissions, revoked_at=None, user_id="u")
    return AuthPrincipal(
        user=SimpleNamespace(is_active=True), key=key, is_full_access=permissions is None
    )


def _request(principal):
    return SimpleNamespace(
        state=SimpleNamespace(principal=principal),
        path_params={"collection_id": str(COLLECTION_ID)},
        headers={},
    )


async def test_scope_authz(fastapi_app) -> None:
    authorize = _route_authorizer(fastapi_app)
    owner = _principal({"capabilities": ["read"], "collections": [str(COLLECTION_ID)]})
    foreign = _principal({"capabilities": ["read"], "collections": [str(uuid.uuid4())]})
    no_read = _principal({"capabilities": ["write"], "collections": [str(COLLECTION_ID)]})
    assert await authorize(_request(owner)) is owner
    for denied in (foreign, no_read):
        with pytest.raises(HTTPException) as exc:
            await authorize(_request(denied))
        assert exc.value.status_code == 403

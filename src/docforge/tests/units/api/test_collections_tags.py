"""Collection ``tags`` round-trip through the router: a create carrying labels persists them onto the
new ``Collection`` row and the response echoes them back; an untagged create returns ``[]`` (never
null). The data layer is mocked — the create façade echoes the row it is handed (as the real one does
once the DB assigns the id), so the assertions pin the router wiring (request → row → response model),
not Postgres. ``CollectionStoreSync.grant_creator_scope`` is stubbed (auth-off root create)."""

import uuid
from unittest.mock import AsyncMock


def _mock_create_db(monkeypatch, echoed_tags_holder: dict) -> None:
    """Wire CONTEXT.database.collections so a create echoes the built row (id assigned) + empty schema."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.routers.collections.store_sync import CollectionStoreSync  # noqa: PLC0415

    async def _create(collection, _rows):
        # Mirror the real façade: the DB assigns the id and applies the column defaults on flush
        # (needs_reindex → False here, since no real flush runs); tags survive verbatim.
        collection.id = uuid.uuid4()
        collection.needs_reindex = False
        echoed_tags_holder["row_tags"] = list(collection.tags)
        return collection

    monkeypatch.setattr(CONTEXT.database.collections, "get_by_name", AsyncMock(return_value=None))
    monkeypatch.setattr(CONTEXT.database.collections, "create", AsyncMock(side_effect=_create))
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=[]))
    monkeypatch.setattr(CollectionStoreSync, "grant_creator_scope", AsyncMock())


def test_create_with_tags_persists_them_and_reads_them_back(client, monkeypatch) -> None:
    holder: dict = {}
    _mock_create_db(monkeypatch, holder)

    response = client.post(
        "/api/v1/collections",
        json={
            "name": "tagged",
            "supported_formats": ["pdf"],
            "tags": ["legal", "demo"],
            "max_file_size_bytes": 1_000_000,
        },
    )

    assert response.status_code == 201, response.text
    # The tags reached the ORM row the façade persisted...
    assert holder["row_tags"] == ["legal", "demo"]
    # ...and the response model echoes them back.
    assert response.json()["tags"] == ["legal", "demo"]


def test_create_without_tags_defaults_to_empty_list(client, monkeypatch) -> None:
    holder: dict = {}
    _mock_create_db(monkeypatch, holder)

    response = client.post(
        "/api/v1/collections",
        json={
            "name": "untagged",
            "supported_formats": ["pdf"],
            "max_file_size_bytes": 1_000_000,
        },
    )

    assert response.status_code == 201, response.text
    # An omitted ``tags`` creates the collection untagged — [] on the row and in the response, never null.
    assert holder["row_tags"] == []
    assert response.json()["tags"] == []

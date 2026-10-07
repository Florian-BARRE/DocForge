"""POST /collections/{id}/chunks/browse — the query-less, filter-only chunk listing (C2).

Route level (ChunkBrowser mocked): the shared filter gate (422s + resolved values + hints), the lean
default shape (no score, no drawing geometry), return_fields, the opaque cursor round-trip, 404, and
READ authz + collection scope. Store level (fake Qdrant client): the (document, chunk_index) order,
keyset pagination across documents, the exclusion filter, and ChunkBrowser's limit+1 → next_cursor.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from shared_libs.public_models import FieldType
from shared_libs.public_models.search import Hit

_COLLECTION = "33333333-3333-3333-3333-333333333333"
_URL = f"/api/v1/collections/{_COLLECTION}/chunks/browse"


def _hit(chunk: int, document: str) -> Hit:
    """A hydrated hit as the read port emits it (geometry + metadata in its bag)."""
    return Hit(
        chunk_id=f"11111111-1111-1111-1111-{chunk:012d}",
        document_id=document,
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


def _wire(monkeypatch, hits: list[Hit], next_cursor=None, stored: list | None = None) -> AsyncMock:
    """Patch the collection reads, the stored-value lookup and the browser; return browse()."""
    from backend.context import CONTEXT  # noqa: PLC0415
    from backend.libs.search import BrowsePage  # noqa: PLC0415

    collection = SimpleNamespace(pipeline={}, search={}, title_field=None)
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    schema = [
        SimpleNamespace(
            field_name="topic", filterable=True, field_type=FieldType.STRING, enum_values=None
        )
    ]
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=schema))
    browse = AsyncMock(return_value=BrowsePage(hits=hits, next_cursor=next_cursor))
    monkeypatch.setattr(CONTEXT, "chunk_browser", SimpleNamespace(browse=browse), raising=False)
    return browse


def _no_resolution(monkeypatch) -> None:
    """Make the stored-value resolution a pass-through (no Postgres)."""
    from backend.libs.search import FilterResolution, SearchFilterResolver  # noqa: PLC0415

    async def _resolve(self, filters, schema, sent=None):
        return FilterResolution(filters=dict(filters or {}), original=dict(sent or {}))

    monkeypatch.setattr(SearchFilterResolver, "resolve", _resolve)


def test_default_page_is_lean_ordered_and_scoreless(client, monkeypatch) -> None:
    """Default fields: no score, no drawing geometry, page_number kept; order is the browser's."""
    from backend.libs.search import BrowseCursor  # noqa: PLC0415

    _no_resolution(monkeypatch)
    cursor = BrowseCursor("doc-b", 4, "11111111-1111-1111-1111-000000000004")
    browse = _wire(monkeypatch, [_hit(3, "doc-a"), _hit(4, "doc-b")], next_cursor=cursor)
    response = client.post(_URL, json={"filters": {"topic": "a"}, "limit": 2})

    assert response.status_code == 200, response.text
    body = response.json()
    assert [chunk["chunk_index"] for chunk in body["chunks"]] == [3, 4]
    for chunk in body["chunks"]:
        assert "score" not in chunk
        assert not {"bbox", "page", "block_ids", "block_locations"} & set(chunk)
        assert chunk["page_number"] == 3 and chunk["document_title"] == "T"
    assert BrowseCursor.decode(body["next_cursor"]) == cursor
    kwargs = browse.await_args.kwargs
    assert kwargs["filters"] == {"topic": "a"} and kwargs["limit"] == 2 and kwargs["cursor"] is None


def test_cursor_round_trips_to_the_browser(client, monkeypatch) -> None:
    """A next_cursor sent back is decoded to the same keyset position; the last page has none."""
    from backend.libs.search import BrowseCursor  # noqa: PLC0415

    browse = _wire(monkeypatch, [])
    cursor = BrowseCursor("doc-a", 7, "c-7")
    body = client.post(_URL, json={"cursor": cursor.encode()}).json()

    assert browse.await_args.kwargs["cursor"] == cursor
    assert body["next_cursor"] is None
    assert browse.await_args.kwargs["filters"] is None


def test_invalid_cursor_is_a_422(client, monkeypatch) -> None:
    """A cursor this API did not issue is rejected before any read."""
    browse = _wire(monkeypatch, [])
    response = client.post(_URL, json={"cursor": "not-a-cursor"})
    assert response.status_code == 422 and "invalid cursor" in response.text
    browse.assert_not_awaited()


def test_return_fields_projection_and_no_score(client, monkeypatch) -> None:
    """return_fields keeps only the requested keys; score is not a browse field (422)."""
    _wire(monkeypatch, [_hit(1, "doc-a")])
    chunk = client.post(_URL, json={"return_fields": ["text", "bbox"]}).json()["chunks"][0]
    assert set(chunk) == {"chunk_id", "document_id", "text", "bbox"}
    response = client.post(_URL, json={"return_fields": ["score"]})
    assert response.status_code == 422 and "score" in response.text


def test_filter_gate_is_shared_with_search(client, monkeypatch) -> None:
    """A non-filterable field / an empty list → the same 422s as search, before the browser runs."""
    browse = _wire(monkeypatch, [])
    assert client.post(_URL, json={"filters": {"secret": "x"}}).status_code == 422
    assert client.post(_URL, json={"filters": {"topic": []}}).status_code == 422
    browse.assert_not_awaited()


def test_empty_first_page_explains_the_filter(client, monkeypatch) -> None:
    """A filtered empty FIRST page carries the zero-hit culprit hint; a later empty page does not."""
    from backend.libs.search import BrowseCursor  # noqa: PLC0415

    _no_resolution(monkeypatch)
    _wire(monkeypatch, [])
    hints = client.post(_URL, json={"filters": {"topic": "zz"}}).json()["hints"]
    assert hints and hints[0]["field"] == "topic"
    later = client.post(
        _URL, json={"filters": {"topic": "zz"}, "cursor": BrowseCursor("d", 1, "c").encode()}
    ).json()
    assert later["hints"] == []


def test_unknown_collection_is_a_404(client, monkeypatch) -> None:
    """No collection → 404."""
    from backend.context import CONTEXT  # noqa: PLC0415

    _wire(monkeypatch, [])
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=None))
    assert client.post(_URL, json={}).status_code == 404


def test_limit_bounds(client, monkeypatch) -> None:
    """limit is 1..200."""
    _wire(monkeypatch, [])
    assert client.post(_URL, json={"limit": 0}).status_code == 422
    assert client.post(_URL, json={"limit": 201}).status_code == 422


async def test_read_capability_and_collection_scope(client) -> None:
    """The route's guard: a READ key scoped to the collection passes; another scope or no READ → 403."""
    import pytest  # noqa: PLC0415
    from fastapi import (
        HTTPException,  # noqa: PLC0415
        routing,  # noqa: PLC0415
    )

    from backend.libs.auth.principal import AuthPrincipal  # noqa: PLC0415

    guard = next(
        sub.call
        for ctx in routing.iter_route_contexts(client.app.routes)
        if ctx.path == "/api/v1/collections/{collection_id}/chunks/browse"
        for sub in ctx.dependant.dependencies
        if sub.call.__qualname__.endswith("require.<locals>._authorize")
    )

    def _request(capabilities: list[str], collections: list[str]) -> SimpleNamespace:
        key = SimpleNamespace(
            permissions={"capabilities": capabilities, "collections": collections},
            revoked_at=None,
            user_id="u",
        )
        principal = AuthPrincipal(
            user=SimpleNamespace(is_active=True), key=key, is_full_access=False
        )
        return SimpleNamespace(
            state=SimpleNamespace(principal=principal), path_params={"collection_id": _COLLECTION}
        )

    assert await guard(_request(["read"], [_COLLECTION]))
    for capabilities, collections in ((["read"], [str(uuid.uuid4())]), (["write"], [_COLLECTION])):
        with pytest.raises(HTTPException) as exc:
            await guard(_request(capabilities, collections))
        assert exc.value.status_code == 403


# ---------------------------------------------------------------- store level


def _record(document_id: str, chunk_index: int, chunk_id: str) -> SimpleNamespace:
    """A scrolled Qdrant record carrying the two order keys."""
    return SimpleNamespace(
        id=chunk_id, payload={"document_id": document_id, "chunk_index": chunk_index}
    )


def _fake_qdrant(points: list[SimpleNamespace]) -> MagicMock:
    """A qdrant client: facet counts per document, scroll returns the batch's points unordered."""
    client = MagicMock()
    counts: dict[str, int] = {}
    for point in points:
        counts[point.payload["document_id"]] = counts.get(point.payload["document_id"], 0) + 1
    client.facet = AsyncMock(
        return_value=SimpleNamespace(
            hits=[SimpleNamespace(value=doc, count=n) for doc, n in counts.items()]
        )
    )

    async def _scroll(collection_name, scroll_filter, limit, offset, with_payload, with_vectors):
        wanted = next(cond.match.any for cond in scroll_filter.must if cond.key == "document_id")
        return [p for p in reversed(points) if p.payload["document_id"] in wanted], None

    client.scroll = AsyncMock(side_effect=_scroll)
    return client


_POINTS = [
    _record("doc-b", 0, "b0"),
    _record("doc-a", 2, "a2"),
    _record("doc-a", 0, "a0"),
    _record("doc-a", 1, "a1"),
    _record("doc-c", 5, "c5"),
]


async def test_browse_api_orders_by_document_then_chunk_index() -> None:
    """Keys come back (document_id, chunk_index) ascending whatever the store order."""
    from shared_libs.services.db.qdrant import QdrantBrowseApi  # noqa: PLC0415

    keys = await QdrantBrowseApi.page(_fake_qdrant(_POINTS), "c", limit=10)
    assert [key[2] for key in keys] == ["a0", "a1", "a2", "b0", "c5"]


async def test_browse_api_keyset_pagination_has_no_gap_or_duplicate() -> None:
    """Walking pages of 2 with the last key as cursor visits every point exactly once, in order."""
    from shared_libs.services.db.qdrant import QdrantBrowseApi  # noqa: PLC0415

    client = _fake_qdrant(_POINTS)
    seen: list[str] = []
    after = None
    while True:
        page = await QdrantBrowseApi.page(client, "c", after=after, limit=2)
        seen.extend(key[2] for key in page)
        if len(page) < 2:
            break
        after = page[-1]
    assert seen == ["a0", "a1", "a2", "b0", "c5"]


async def test_facade_browse_applies_the_searchability_exclusion() -> None:
    """browse_keys sends the enabled==false must_not (and the filter) to both facet and scroll."""
    from shared_libs.services.db.facades import SearchFacade  # noqa: PLC0415
    from shared_libs.services.db.qdrant import Match  # noqa: PLC0415

    qdrant = MagicMock()
    qdrant.raw = _fake_qdrant(_POINTS)
    qdrant.raw.collection_exists = AsyncMock(return_value=True)
    postgres = MagicMock()
    session = MagicMock()
    postgres.session.return_value.__aenter__ = AsyncMock(return_value=session)
    postgres.session.return_value.__aexit__ = AsyncMock(return_value=None)
    facade = SearchFacade(postgres, qdrant)

    import shared_libs.services.db.facades.search_facade as module  # noqa: PLC0415

    original = module.DocumentApi.list_disabled_ids
    module.DocumentApi.list_disabled_ids = AsyncMock(return_value=[])
    try:
        keys = await facade.browse_keys(
            uuid.uuid4(), conditions=[Match(field="topic", value="a")], limit=3
        )
    finally:
        module.DocumentApi.list_disabled_ids = original

    assert [key[2] for key in keys] == ["a0", "a1", "a2"]
    facet_filter = qdrant.raw.facet.await_args.kwargs["facet_filter"]
    assert (
        facet_filter.must_not[0].key == "enabled" and facet_filter.must_not[0].match.value is False
    )
    assert facet_filter.must[0].key == "topic"


async def test_facade_browse_on_an_uningested_collection_is_empty() -> None:
    """No Qdrant space yet → an empty page, Postgres untouched."""
    from shared_libs.services.db.facades import SearchFacade  # noqa: PLC0415

    qdrant = MagicMock()
    qdrant.raw.collection_exists = AsyncMock(return_value=False)
    postgres = MagicMock()
    assert await SearchFacade(postgres, qdrant).browse_keys(uuid.uuid4()) == []
    postgres.session.assert_not_called()


async def test_chunk_browser_cursor_and_hydration_order(fastapi_app, monkeypatch) -> None:
    """limit+1 keys → next_cursor = the last kept key; hits keep the key order, vanished rows drop."""
    from backend.libs.search import BrowseCursor, ChunkBrowser  # noqa: PLC0415
    from backend.libs.search.read_port import CollectionReadPortImpl  # noqa: PLC0415

    database = MagicMock()
    database.search.browse_keys = AsyncMock(
        return_value=[("a", 0, "a0"), ("a", 1, "a1"), ("b", 0, "b0")]
    )

    async def _hydrate(self, chunk_ids):
        return {cid: Hit(chunk_id=cid, document_id=cid[0]) for cid in chunk_ids if cid != "a1"}

    monkeypatch.setattr(CollectionReadPortImpl, "hydrate", _hydrate)
    page = await ChunkBrowser(database).browse(uuid.uuid4(), filters={"topic": "a"}, limit=2)

    assert [hit.chunk_id for hit in page.hits] == ["a0"]
    assert page.next_cursor == BrowseCursor("a", 1, "a1")
    kwargs = database.search.browse_keys.await_args.kwargs
    assert kwargs["limit"] == 3 and kwargs["after"] is None
    assert kwargs["conditions"][0].field == "topic"

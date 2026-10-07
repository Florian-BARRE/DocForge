"""The search response carries the termless-lexical-target hint the read port recorded on the probe
(a stopword-only query against a BM25 metadata lexical target). Service mocked; ``from backend...``
imports are deferred until after ``fastapi_app``.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from shared_libs.public_models.search import SearchResult

_URL = "/api/v1/collections/33333333-3333-3333-3333-333333333333/search"


def test_search_response_carries_the_termless_hint(client, fastapi_app, monkeypatch) -> None:
    from backend.context import CONTEXT  # noqa: PLC0415

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
    collection = SimpleNamespace(pipeline=pipeline, search={})
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=[]))

    async def _search_stub(*args, probe=None, **kwargs):
        probe.record_termless_lexical(["nom"])
        return SearchResult(query="le", hits=[]), (0, 0, None, 0)

    monkeypatch.setattr(CONTEXT.search_service, "search", _search_stub)

    response = client.post(_URL, json={"query": "le"})

    assert response.status_code == 200, response.text
    hints = response.json()["hints"]
    assert [h["field"] for h in hints] == ["nom"]
    assert "only stopwords" in hints[0]["message"]

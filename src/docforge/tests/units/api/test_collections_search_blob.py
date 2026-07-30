"""Collections router: the ``search`` column is a SEARCH GRAPH BLOB now (the search analog of
``pipeline``), validated on write exactly like the pipeline blob.

A PATCH carrying a structurally broken search blob (a node kind the registry does not know) must be
rejected 422 BEFORE storage — update_config is never reached, so the stored value cannot change. A
valid search blob is stored verbatim. The empty ``{}`` sentinel ("use the stock default") is always
allowed through, unvalidated. CONTEXT is patched with recording fakes so the endpoint runs without a
store; ``from backend...`` imports are deferred until after the ``fastapi_app`` fixture put app/ on
sys.path.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

# A search blob naming a query node kind the registry does not know — BuildError at build time.
BROKEN_SEARCH_BLOB = {
    "id": "search_pipeline",
    "nodes": [{"id": "normalize", "family": "query", "kind": "does_not_exist", "config": {}}],
    "transitions": [],
    "bindings": {},
}


def _valid_search_blob() -> dict:
    """The stock search topology, serialised — a known-good graph blob."""
    from shared_libs.pipelines.search import SearchPipeline  # noqa: PLC0415

    return SearchPipeline.default_blob().model_dump(mode="json")


def _non_search_topology() -> dict:
    """The stock search graph with its deliver/hits terminal removed — still builds structurally,
    but its terminal (hydrate) produces RankedHits, not a SearchResult, so it is NOT a search
    pipeline. Mirrors the live-proof case that predated the terminal-contract check."""
    blob = _valid_search_blob()
    blob["nodes"] = [n for n in blob["nodes"] if n["id"] != "deliver"]
    blob["transitions"] = [t for t in blob["transitions"] if t["to_node_id"] != "deliver"]
    blob["bindings"] = {k: v for k, v in blob["bindings"].items() if k != "deliver"}
    return blob


def _install_recording_context(monkeypatch, fastapi_app, stored_search: dict) -> SimpleNamespace:
    """Patch CONTEXT.database.collections with a collection + a recording update_config spy."""
    # 1. Deferred import — app/ is on sys.path only after fastapi_app booted.
    from backend.context import CONTEXT  # noqa: PLC0415

    # 2. An existing collection carrying the current stored search blob.
    collection = SimpleNamespace(
        id=uuid.uuid4(),
        name="c1",
        supported_formats=["pdf"],
        max_file_size_bytes=1_000_000,
        needs_reindex=False,
        created_at=None,
        pipeline={},
        search=stored_search,
    )
    collections = SimpleNamespace(
        get=AsyncMock(return_value=collection),
        get_by_name=AsyncMock(return_value=None),
        get_schema=AsyncMock(return_value=[]),
        update_config=AsyncMock(),
    )
    monkeypatch.setattr(CONTEXT, "database", SimpleNamespace(collections=collections))
    return SimpleNamespace(collections=collections, collection=collection)


def test_patch_broken_search_blob_is_422_and_not_stored(client, fastapi_app, monkeypatch) -> None:
    """A structurally broken search blob is rejected 422 before update_config is ever reached."""
    spies = _install_recording_context(monkeypatch, fastapi_app, stored_search={})

    response = client.patch(
        f"/api/v1/collections/{uuid.uuid4()}",
        json={"search": BROKEN_SEARCH_BLOB},
    )

    # 1. A broken graph blob is DATA → 422 (never a 500), naming the offending kind.
    assert response.status_code == 422, response.text
    assert "does_not_exist" in response.text

    # 2. Nothing was stored — the config write was never reached.
    spies.collections.update_config.assert_not_called()


def test_patch_valid_search_blob_is_stored(client, fastapi_app, monkeypatch) -> None:
    """A valid search blob passes validation and reaches storage verbatim."""
    spies = _install_recording_context(monkeypatch, fastapi_app, stored_search={})
    blob = _valid_search_blob()

    response = client.patch(
        f"/api/v1/collections/{uuid.uuid4()}",
        json={"search": blob},
    )

    # 1. Accepted, and the stored search blob is exactly what was sent.
    assert response.status_code == 200, response.text
    spies.collections.update_config.assert_awaited_once()
    assert spies.collections.update_config.await_args.kwargs["search"] == blob


def test_patch_empty_search_sentinel_is_allowed(client, fastapi_app, monkeypatch) -> None:
    """The {} sentinel ('use the stock default') is stored unvalidated."""
    spies = _install_recording_context(monkeypatch, fastapi_app, stored_search=_valid_search_blob())

    response = client.patch(
        f"/api/v1/collections/{uuid.uuid4()}",
        json={"search": {}},
    )

    # 1. Empty blob is always allowed and reaches storage as {}.
    assert response.status_code == 200, response.text
    assert spies.collections.update_config.await_args.kwargs["search"] == {}


def test_patch_non_search_topology_is_422_and_not_stored(client, fastapi_app, monkeypatch) -> None:
    """A structurally-valid graph that is NOT a search pipeline (no SearchResult terminal) is
    rejected 422 at write — it can never reach storage to 500 on every subsequent query."""
    spies = _install_recording_context(monkeypatch, fastapi_app, stored_search={})

    response = client.patch(
        f"/api/v1/collections/{uuid.uuid4()}",
        json={"search": _non_search_topology()},
    )

    # 1. The terminal-contract check rejects it with a clear message.
    assert response.status_code == 422, response.text
    assert "not a valid search pipeline" in response.text

    # 2. Nothing was stored — the config write was never reached.
    spies.collections.update_config.assert_not_called()


def test_patch_non_empty_search_without_nodes_is_422(client, fastapi_app, monkeypatch) -> None:
    """A non-empty search dict lacking a 'nodes' key (e.g. a legacy tuning dict) is rejected 422 —
    it would otherwise be stored then silently discarded at read."""
    spies = _install_recording_context(monkeypatch, fastapi_app, stored_search={})

    response = client.patch(
        f"/api/v1/collections/{uuid.uuid4()}",
        json={"search": {"rescore_pool_size": 50}},
    )

    # 1. Only {} or a real topology (has "nodes") is a valid search value.
    assert response.status_code == 422, response.text
    assert "nodes" in response.text
    spies.collections.update_config.assert_not_called()

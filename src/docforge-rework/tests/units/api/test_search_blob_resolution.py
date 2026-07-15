"""SearchService: the STORED-blob resolution + pool-size injection — the new seam that runs the
collection's own search graph when it carries one, else the stock default.

These exercise the pure resolution logic (no DB, no runner): a collection whose ``search`` has a
``"nodes"`` list runs THAT topology; ``{}`` (or anything without ``"nodes"``) resolves to the stock
default; and a per-query pool override lands on the resolved blob's retrieve node. ``from backend...``
imports are deferred until after ``fastapi_app`` registered app/ on sys.path. End-to-end run wiring is
covered live (see the phase's live proof) — this isolates the branch that picks the blob.
"""

from types import SimpleNamespace


def _service(fastapi_app):
    """A SearchService with a dummy database — resolution never touches it."""
    from backend.libs.search.service import SearchService  # noqa: PLC0415

    return SearchService(database=SimpleNamespace())


def test_empty_search_resolves_to_stock_default(fastapi_app) -> None:
    """A {} sentinel resolves to the serialised stock default (a real 'nodes' graph)."""
    from shared_libs.pipelines.search import SearchPipeline  # noqa: PLC0415

    service = _service(fastapi_app)
    resolved = service._SearchService__resolve_blob({})

    # 1. The fallback is the stock topology in plain-dict form.
    assert resolved == SearchPipeline.default_blob().model_dump(mode="json")
    assert resolved.get("nodes"), "the resolved default must carry a nodes list"


def test_non_graph_value_resolves_to_stock_default(fastapi_app) -> None:
    """Anything without a 'nodes' key is the sentinel → stock default."""
    service = _service(fastapi_app)
    assert service._SearchService__resolve_blob({"foo": "bar"}).get("nodes")


def test_stored_graph_is_run_verbatim(fastapi_app) -> None:
    """A stored blob carrying a 'nodes' list is the collection's OWN topology — returned as-is."""
    service = _service(fastapi_app)
    stored = {"id": "custom", "nodes": [{"id": "n", "family": "query", "kind": "normalize"}]}
    assert service._SearchService__resolve_blob(stored) is stored


def test_pool_override_lands_on_retrieve_node(fastapi_app) -> None:
    """The per-query pool override is written onto the resolved blob's retrieve node config."""
    from shared_libs.pipelines.search import SearchPipeline  # noqa: PLC0415

    service = _service(fastapi_app)
    blob = SearchPipeline.default_blob().model_dump(mode="json")

    service._SearchService__inject_rescore_pool_size(blob, 7)

    retrieve = next(n for n in blob["nodes"] if n["id"] == "retrieve")
    assert retrieve["config"]["rescore_pool_size"] == 7

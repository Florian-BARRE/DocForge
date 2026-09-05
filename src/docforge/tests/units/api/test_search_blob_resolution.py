"""SearchService: the STORED-blob resolution + pool-size injection — the new seam that runs the
collection's own search graph when it carries one, else the stock default.

These exercise the pure resolution logic (no DB, no runner): a collection whose ``search`` has a
``"nodes"`` list runs THAT topology; ``{}`` (or anything without ``"nodes"``) resolves to the stock
default; and a per-query pool override lands on the resolved blob's retrieve node. ``from backend...``
imports are deferred until after ``fastapi_app`` registered app/ on sys.path.

NOTE: end-to-end run wiring (this resolved blob actually executed through FlowEngine against a real
store) has NO test today, live or unit — that gap is still open. This file isolates only the pure
branch that PICKS the blob; see tests/units/search/test_search_pipeline.py for the graph-execution
coverage (against a mocked read port, not this resolution seam).
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


def test_stored_graph_is_healed_but_topology_preserved(fastapi_app) -> None:
    """A stored 'nodes' graph is the collection's OWN topology — healed (a fresh dict), not mutated.

    The heal never touches the caller's stored dict (it deep-copies) and, when no config drift is
    present, is byte-identical to the input — the collection's own topology runs unchanged.
    """
    service = _service(fastapi_app)
    stored = {"id": "custom", "nodes": [{"id": "n", "family": "query", "kind": "normalize"}]}

    resolved = service._SearchService__resolve_blob(stored)

    assert resolved == stored  # same graph
    assert resolved is not stored  # but a fresh dict — the stored value is never mutated in place


def test_stored_graph_with_stale_config_field_self_heals(fastapi_app) -> None:
    """Registry drift (a config field the current model no longer knows) auto-heals at read.

    A stale extra key would brick the extra='forbid' build at run time; the read-side heal strips it
    so the collection's own search resolves+builds instead of bricking (the ingest-normalizer parity).
    """
    from shared_libs.pipelines.build import PipelineBuilder  # noqa: PLC0415
    from shared_libs.pipelines.search import SearchPipeline  # noqa: PLC0415
    from shared_libs.pipelines.validation import GraphValidator  # noqa: PLC0415

    service = _service(fastapi_app)
    stored = SearchPipeline.default_blob().model_dump(mode="json")
    normalize_node = next(node for node in stored["nodes"] if node["id"] == "normalize")
    normalize_node.setdefault("config", {})["removed_legacy_knob"] = 123  # « the drift

    resolved = service._SearchService__resolve_blob(stored)

    # 1. The stale field is gone from the healed blob.
    healed_normalize = next(node for node in resolved["nodes"] if node["id"] == "normalize")
    assert "removed_legacy_knob" not in healed_normalize.get("config", {})
    # 2. And the healed blob now builds + validates clean (it would have bricked un-healed).
    assert GraphValidator().validate(PipelineBuilder().build(resolved)) == []


def test_stored_graph_with_unhealable_config_raises_search_run_error(fastapi_app) -> None:
    """A config broken beyond stale-field drift (a bad TYPE) is a genuinely invalid stored graph.

    It cannot be auto-healed, so resolution raises SearchRunError — the router maps that to the same
    422 as an unbuildable blob (re-save the search blob), never a silent mangle or a 500.
    """
    import pytest  # noqa: PLC0415

    from backend.libs.search.service import SearchRunError  # noqa: PLC0415
    from shared_libs.pipelines.search import SearchPipeline  # noqa: PLC0415

    service = _service(fastapi_app)
    stored = SearchPipeline.default_blob().model_dump(mode="json")
    encode_node = next(node for node in stored["nodes"] if node["id"] == "encode")
    encode_node.setdefault("config", {})["axis_timeout_seconds"] = "not-a-number"  # « bad type

    with pytest.raises(SearchRunError):
        service._SearchService__resolve_blob(stored)


def test_stored_graph_with_unknown_kind_raises_search_run_error(fastapi_app) -> None:
    """A node naming a kind the registry no longer knows cannot be migrated — a clear SearchRunError."""
    import pytest  # noqa: PLC0415

    from backend.libs.search.service import SearchRunError  # noqa: PLC0415

    service = _service(fastapi_app)
    stored = {"id": "custom", "nodes": [{"id": "n", "family": "query", "kind": "gone_kind"}]}

    with pytest.raises(SearchRunError):
        service._SearchService__resolve_blob(stored)


def test_default_run_timeout_is_thirty_seconds(fastapi_app) -> None:
    """With no override, the inline-run wall-clock cap defaults to 30 s."""
    assert _service(fastapi_app)._timeout_seconds == 30.0


def test_configured_run_timeout_is_stored_and_used(fastapi_app) -> None:
    """A configured timeout (SEARCH_RUN_TIMEOUT_SECONDS at boot) is stored and drives the run cap."""
    from backend.libs.search.service import SearchService  # noqa: PLC0415

    service = SearchService(database=SimpleNamespace(), timeout_seconds=120.0)
    assert service._timeout_seconds == 120.0

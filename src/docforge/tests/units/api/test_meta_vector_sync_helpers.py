"""MetaVectorSyncHelpers — the pure, I/O-free conventions MetaVectorSyncFacade leans on:
rendering a document-scope value to embeddable text, locating the collection's embed node in a
(possibly nested) ingestion blob, and rebuilding the embedder from its stored kind/config
(extra="forbid" — a drifted blob fails loudly)."""

import pytest
from pydantic import ValidationError

from shared_libs.services.db.facades.meta_vector_sync_helpers import MetaVectorSyncHelpers


# ---------------------- render_value ---------------------- #
def test_render_value_joins_a_list_with_comma_space() -> None:
    assert MetaVectorSyncHelpers.render_value(["a", "b", "c"]) == "a, b, c"


def test_render_value_stringifies_a_scalar() -> None:
    assert MetaVectorSyncHelpers.render_value(42) == "42"


def test_render_value_empty_string_renders_to_none() -> None:
    assert MetaVectorSyncHelpers.render_value("") is None


def test_render_value_whitespace_only_renders_to_none() -> None:
    assert MetaVectorSyncHelpers.render_value("   ") is None


def test_render_value_empty_list_renders_to_none() -> None:
    assert MetaVectorSyncHelpers.render_value([]) is None


# ---------------------- find_embed_node ---------------------- #
def _leaf(node_id: str, family: str, kind: str) -> dict:
    return {"id": node_id, "family": family, "kind": kind, "config": {}}


def test_find_embed_node_none_when_absent() -> None:
    blob = {"nodes": [_leaf("a", "parser", "docling"), _leaf("b", "chunker", "fixed_size")]}
    assert MetaVectorSyncHelpers.find_embed_node(blob) is None


def test_find_embed_node_at_top_level() -> None:
    blob = {"nodes": [_leaf("a", "parser", "docling"), _leaf("e", "embed", "bge_server")]}
    node = MetaVectorSyncHelpers.find_embed_node(blob)
    assert node is not None
    assert node["id"] == "e"


def test_find_embed_node_descends_nested_group_and_foreach() -> None:
    """A foreach wraps a group ('body') which holds children ('nodes') — descend through both."""
    blob = {
        "nodes": [
            _leaf("a", "parser", "docling"),
            {
                "body": {
                    "nodes": [
                        _leaf("c", "chunker", "fixed_size"),
                        _leaf("e", "embed", "bge_server"),
                    ]
                }
            },
        ]
    }
    node = MetaVectorSyncHelpers.find_embed_node(blob)
    assert node is not None
    assert node["id"] == "e"


# ---------------------- rebuild_embedder ---------------------- #
def test_rebuild_embedder_builds_a_working_instance() -> None:
    import shared_libs.pipelines.nodes.embed  # noqa: F401 — registers "embed" kinds

    embed_node = {"kind": "bge_server", "config": {"model": "BAAI/bge-m3", "base_url": "http://x"}}
    embedder, config = MetaVectorSyncHelpers.rebuild_embedder(embed_node)
    assert embedder is not None
    assert config.model == "BAAI/bge-m3"


def test_rebuild_embedder_drifted_config_raises_validation_error() -> None:
    import shared_libs.pipelines.nodes.embed  # noqa: F401 — registers "embed" kinds

    embed_node = {
        "kind": "bge_server",
        "config": {"model": "BAAI/bge-m3", "base_url": "http://x", "not_a_real_key": True},
    }
    with pytest.raises(ValidationError):
        MetaVectorSyncHelpers.rebuild_embedder(embed_node)

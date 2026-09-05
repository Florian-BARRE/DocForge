"""SearchBlobNormalizer — the read-side auto-heal of a stored search blob (the search analog of the
ingest BlobNormalizer). It reconciles each action node's stored config to its CURRENT registered
model: a clean blob passes through byte-identical, registry drift (a stale config field the model no
longer declares) is stripped so the extra='forbid' build no longer bricks, and a config broken beyond
drift — or a kind the registry no longer knows — raises a clear SearchBlobNormalizationError. A {}
sentinel is a no-op. No engine execution, no store.
"""

import pytest

from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.search import (
    SearchBlobNormalizationError,
    SearchBlobNormalizer,
    SearchPipeline,
)
from shared_libs.pipelines.validation import GraphValidator


def test_empty_sentinel_is_a_noop() -> None:
    """A {} blob (the stock-default sentinel) carries no stored config — returned unchanged."""
    assert SearchBlobNormalizer.normalize({}) == {}


def test_non_graph_value_is_a_noop() -> None:
    """Anything without a 'nodes' key is the sentinel — nothing to heal."""
    assert SearchBlobNormalizer.normalize({"foo": "bar"}) == {"foo": "bar"}


def test_clean_blob_passes_through_equal_and_never_mutates_input() -> None:
    """A drift-free stored blob heals to an EQUAL but distinct dict (the input is never mutated)."""
    stored = SearchPipeline.default_blob().model_dump(mode="json")
    before = stored.copy()

    healed = SearchBlobNormalizer.normalize(stored)

    assert healed == stored
    assert stored == before  # the caller's dict is untouched (deep-copied heal)


def test_stale_config_field_is_stripped_and_result_builds() -> None:
    """Registry drift (an unknown config key) is stripped so the healed blob builds clean."""
    stored = SearchPipeline.default_blob().model_dump(mode="json")
    encode = next(node for node in stored["nodes"] if node["id"] == "encode")
    encode.setdefault("config", {})["removed_knob"] = "stale"  # « a field the model dropped

    healed = SearchBlobNormalizer.normalize(stored)

    healed_encode = next(node for node in healed["nodes"] if node["id"] == "encode")
    assert "removed_knob" not in healed_encode["config"]
    # The un-healed blob would raise at build (extra='forbid'); the healed one validates clean.
    assert GraphValidator().validate(PipelineBuilder().build(healed)) == []


def test_valid_config_value_is_preserved_through_the_heal() -> None:
    """A legitimate non-default config value survives the heal (only stale keys are dropped)."""
    stored = SearchPipeline.default_blob().model_dump(mode="json")
    encode = next(node for node in stored["nodes"] if node["id"] == "encode")
    encode.setdefault("config", {})["axis_timeout_seconds"] = 3.5
    encode["config"]["removed_knob"] = "stale"

    healed = SearchBlobNormalizer.normalize(stored)

    healed_encode = next(node for node in healed["nodes"] if node["id"] == "encode")
    assert healed_encode["config"]["axis_timeout_seconds"] == 3.5
    assert "removed_knob" not in healed_encode["config"]


def test_bad_config_type_is_not_healed_but_raised() -> None:
    """A config broken by a bad TYPE (not stale-key drift) raises — never silently mangled."""
    stored = SearchPipeline.default_blob().model_dump(mode="json")
    encode = next(node for node in stored["nodes"] if node["id"] == "encode")
    encode.setdefault("config", {})["axis_timeout_seconds"] = "not-a-number"

    with pytest.raises(SearchBlobNormalizationError):
        SearchBlobNormalizer.normalize(stored)


def test_unknown_kind_raises() -> None:
    """A node whose (family, kind) the registry no longer knows cannot be migrated — it raises."""
    stored = {"id": "g", "nodes": [{"id": "n", "family": "query", "kind": "gone_kind"}]}
    with pytest.raises(SearchBlobNormalizationError):
        SearchBlobNormalizer.normalize(stored)


def test_stale_field_inside_a_nested_group_is_healed() -> None:
    """The heal recurses nested groups — a stale key on a node inside a group is stripped too."""
    stored = {
        "id": "root",
        "nodes": [
            {
                "id": "inner",
                "nodes": [
                    {
                        "id": "encode",
                        "family": "encode",
                        "kind": "collection",
                        "config": {"removed_knob": 1},
                    }
                ],
            }
        ],
    }

    healed = SearchBlobNormalizer.normalize(stored)

    inner_encode = healed["nodes"][0]["nodes"][0]
    assert "removed_knob" not in inner_encode["config"]

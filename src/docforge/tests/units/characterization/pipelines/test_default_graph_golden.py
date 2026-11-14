# ====== Code Summary ======
# Characterization of the built pipeline graphs (safety net for the engine and validation refactors).
# The stock blobs — the default ingest graph, every other ingest preset and every search preset — are
# built with the PipelineBuilder, validated, and their TOPOLOGY snapshotted: node ids, kinds, node types,
# error policies, Consumes/Produces slot names, ForEach loops, transitions (with their conditions) and
# data bindings. A second golden records what the builder / validators answer for a few deliberately
# broken variants of the default blob (issue code, location, message). No provider is contacted: the
# builder and validators check topology and config shape only. Node configs are NOT captured here — the
# byte-for-byte default blob lives in tests/units/stages/test_default_blob_golden.py. A drifted golden is
# a refactoring decision to review (see support/golden_file.py), never a test to fix.

# ====== Standard Library Imports ======
import copy
from typing import Any

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.search import SearchPipeline
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.pipelines.validation.blob import BlobStructureValidator, BlobValidationError

# ====== Local Project Imports ======
from .support.golden_file import GoldenFile
from .support.graph_outline import GraphOutline

TOPOLOGY_GOLDEN = GoldenFile("graph_topology.json")
VALIDATION_GOLDEN = GoldenFile("graph_validation_issues.json")

FACADES = {"ingest": IngestPipeline, "search": SearchPipeline}
PRESETS = [
    (facade_name, preset.name)
    for facade_name, facade in FACADES.items()
    for preset in facade.presets()
]


@pytest.mark.parametrize(("facade_name", "preset"), PRESETS, ids=[f"{f}.{p}" for f, p in PRESETS])
def test_preset_graph_topology_matches_its_golden(facade_name: str, preset: str) -> None:
    blob = FACADES[facade_name].preset_blob(preset).model_dump(mode="json")
    group = PipelineBuilder().build(blob)
    assert GraphValidator().validate(group) == []
    TOPOLOGY_GOLDEN.check(f"{facade_name}.{preset}", GraphOutline.node(group))


def _default_ingest_blob() -> dict[str, Any]:
    return copy.deepcopy(IngestPipeline.default_blob().model_dump(mode="json"))


def _without_embed_binding(blob: dict[str, Any]) -> None:
    blob["bindings"]["embed"] = {}


def _dangling_transition(blob: dict[str, Any]) -> None:
    blob["transitions"].append({"from_node_id": "bundle", "to_node_id": "ghost"})


def _cycle(blob: dict[str, Any]) -> None:
    blob["transitions"].append({"from_node_id": "bundle", "to_node_id": "probe"})


def _second_parser(blob: dict[str, Any]) -> None:
    clone = copy.deepcopy(next(node for node in blob["nodes"] if node["id"] == "parse"))
    clone["id"] = "parse_again"
    blob["nodes"].append(clone)


def _unknown_kind(blob: dict[str, Any]) -> None:
    next(node for node in blob["nodes"] if node["id"] == "parse")["kind"] = "no_such_parser"


BROKEN_VARIANTS = {
    "embed_slot_unbound": _without_embed_binding,
    "transition_to_unknown_node": _dangling_transition,
    "transition_closing_a_cycle": _cycle,
    "second_unique_parser": _second_parser,
    "unknown_node_kind": _unknown_kind,
}


@pytest.mark.parametrize("variant", list(BROKEN_VARIANTS))
def test_broken_default_blob_is_reported_as_its_golden(variant: str) -> None:
    blob = _default_ingest_blob()
    BROKEN_VARIANTS[variant](blob)
    with pytest.raises(BlobValidationError) as raised:
        BlobStructureValidator().validate_ingest(blob)
    VALIDATION_GOLDEN.check(
        variant,
        {
            "message": str(raised.value),
            "issues": [
                {"code": issue.code.value, "location": issue.location, "message": issue.message}
                for issue in raised.value.issues
            ],
        },
    )


def test_search_blob_is_rejected_by_the_ingest_palette() -> None:
    blob = SearchPipeline.default_blob().model_dump(mode="json")
    with pytest.raises(BlobValidationError) as raised:
        BlobStructureValidator().validate_ingest(blob)
    VALIDATION_GOLDEN.check(
        "search_blob_in_ingest_palette",
        {
            "issue_count": len(raised.value.issues),
            "codes": sorted({issue.code.value for issue in raised.value.issues}),
        },
    )

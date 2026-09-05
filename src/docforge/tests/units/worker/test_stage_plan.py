"""StagePlanHelpers.planned_stage_ids — the progress DENOMINATOR basis.

The planned (happy) path is the walk from the graph's single entry following every edge EXCEPT the
escalation/fallback ones (ScoreBelow / OnFailure). A fallback provider reachable ONLY through those
never runs on a successful pass, so counting it would understate the percentage. These tests cover the
algorithm on hand-built blobs (linear, escalation, degenerate) AND on the REAL compiled topology, so a
future change to how a chain expands into top-level nodes cannot silently regress the denominator.

StagePlanHelpers is pure (stdlib only), imported as ``jobs.stage_plan`` once jobs.core has loaded it.
"""

import sys

import pytest

from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.stages.compiler import StageCompiler
from shared_libs.pipelines.ingest.stages.models import ChainStep, SetChain


@pytest.fixture
def stage_plan(worker_jobs_modules):
    """The jobs.stage_plan module (imported as a side effect of jobs.core under the fake backend)."""
    return sys.modules["jobs.stage_plan"]


def _edge(src: str, dst: str, kind: str) -> dict:
    return {"from_node_id": src, "to_node_id": dst, "condition": {"kind": kind}}


def test_empty_blob_plans_nothing(stage_plan) -> None:
    assert stage_plan.StagePlanHelpers.planned_stage_ids({}) == []


def test_linear_blob_plans_every_stage(stage_plan) -> None:
    blob = {
        "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        "transitions": [_edge("a", "b", "on_success"), _edge("b", "c", "on_success")],
    }
    assert stage_plan.StagePlanHelpers.planned_stage_ids(blob) == ["a", "b", "c"]


def test_escalation_roots_are_excluded_from_the_plan(stage_plan) -> None:
    # parse_1 / parse_2 are reachable ONLY via score_below / on_failure — never on a good run.
    blob = {
        "nodes": [{"id": n} for n in ("address", "parse_0", "parse_1", "parse_2", "figures")],
        "transitions": [
            _edge("address", "parse_0", "on_success"),
            _edge("parse_0", "parse_1", "score_below"),
            _edge("parse_0", "parse_1", "on_failure"),
            _edge("parse_1", "parse_2", "score_below"),
            _edge("parse_1", "parse_2", "on_failure"),
            _edge("parse_0", "figures", "on_success"),
            _edge("parse_1", "figures", "on_success"),
            _edge("parse_2", "figures", "on_success"),
        ],
    }
    planned = stage_plan.StagePlanHelpers.planned_stage_ids(blob)

    assert planned == ["address", "parse_0", "figures"]
    assert "parse_1" not in planned and "parse_2" not in planned


def test_node_reachable_by_both_normal_and_escalation_edge_is_kept(stage_plan) -> None:
    # convergence is reached from the primary via on_success AND from the fallback via on_failure —
    # it is on the happy path, so it counts.
    blob = {
        "nodes": [{"id": n} for n in ("primary", "fallback", "convergence")],
        "transitions": [
            _edge("primary", "fallback", "on_failure"),
            _edge("primary", "convergence", "on_success"),
            _edge("fallback", "convergence", "on_success"),
        ],
    }
    planned = stage_plan.StagePlanHelpers.planned_stage_ids(blob)

    assert planned == ["primary", "convergence"]
    assert "fallback" not in planned


def test_no_single_entry_falls_back_to_every_node(stage_plan) -> None:
    # Two entries (a malformed/edited blob): never understate — count every top-level node.
    blob = {
        "nodes": [{"id": "x"}, {"id": "y"}],
        "transitions": [],  # both are entries (neither is a target)
    }
    assert stage_plan.StagePlanHelpers.planned_stage_ids(blob) == ["x", "y"]


def test_real_default_blob_plans_all_top_level_stages(stage_plan) -> None:
    # The stock ingestion blob is a linear chain — the plan is exactly its top-level ids, in order.
    blob = IngestPipeline.default_blob().model_dump(mode="json")
    top_level = [node["id"] for node in blob["nodes"]]

    assert stage_plan.StagePlanHelpers.planned_stage_ids(blob) == top_level


def test_real_compiled_parser_escalation_excludes_fallback_steps(stage_plan) -> None:
    # A real 3-provider parser chain compiles to parse_0/parse_1/parse_2 with score_below+on_failure
    # escalation edges; the plan keeps only parse_0 (the primary), dropping the two fallbacks.
    blob = IngestPipeline.default_blob()
    action = SetChain(
        stage="parse",
        steps=[
            ChainStep(kind="docling", score_below=0.7),
            ChainStep(kind="granite_docling", score_below=0.5),
            ChainStep(kind="pp_structure"),
        ],
    )
    compiled, _notices = StageCompiler().apply(blob, action)
    planned = stage_plan.StagePlanHelpers.planned_stage_ids(compiled.model_dump(mode="json"))

    assert "parse_0" in planned
    assert "parse_1" not in planned and "parse_2" not in planned
